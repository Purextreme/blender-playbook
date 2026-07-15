"""Restore a normalized uint8 GLB COLOR_0 attribute onto a Blender point cloud.

Run inside Blender, for example:
blender file.blend --python restore_glb_point_colors.py -- --glb input.glb --object geometry_0

The function can also be imported or sent through a Blender Python bridge.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

import bpy
import numpy as np


def _read_glb(path: Path) -> tuple[dict, bytes]:
    with path.open("rb") as handle:
        magic, version, total_length = struct.unpack("<4sII", handle.read(12))
        if magic != b"glTF" or version != 2:
            raise RuntimeError("Expected a GLB 2.0 file")

        document = None
        binary = None
        while handle.tell() < total_length:
            chunk_length, chunk_type = struct.unpack("<II", handle.read(8))
            chunk = handle.read(chunk_length)
            if chunk_type == 0x4E4F534A:
                document = json.loads(chunk.decode("utf-8").rstrip("\x00 "))
            elif chunk_type == 0x004E4942:
                binary = chunk

    if document is None or binary is None:
        raise RuntimeError("GLB must contain both JSON and BIN chunks")
    return document, binary


def _srgb_to_linear(rgb: np.ndarray) -> np.ndarray:
    return np.where(
        rgb <= 0.04045,
        rgb / 12.92,
        ((rgb + 0.055) / 1.055) ** 2.4,
    ).astype(np.float32)


def _decode_color_0(
    document: dict,
    binary: bytes,
    mesh_index: int,
    primitive_index: int,
    convert_srgb: bool,
) -> np.ndarray:
    primitive = document["meshes"][mesh_index]["primitives"][primitive_index]
    if primitive.get("mode", 4) != 0:
        raise RuntimeError("Target primitive is not glTF POINTS mode (0)")
    if "COLOR_0" not in primitive.get("attributes", {}):
        raise RuntimeError("Target primitive has no COLOR_0 attribute")

    accessor = document["accessors"][primitive["attributes"]["COLOR_0"]]
    if accessor.get("componentType") != 5121:
        raise RuntimeError("Only normalized unsigned-byte COLOR_0 is supported")
    if not accessor.get("normalized", False):
        raise RuntimeError("Unsigned-byte COLOR_0 must be normalized")

    vector_type = accessor.get("type")
    components = {"VEC3": 3, "VEC4": 4}.get(vector_type)
    if components is None:
        raise RuntimeError("Only VEC3 and VEC4 COLOR_0 accessors are supported")

    view = document["bufferViews"][accessor["bufferView"]]
    count = accessor["count"]
    start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    stride = view.get("byteStride", components)
    raw = np.frombuffer(binary, dtype=np.uint8)

    if stride == components:
        values = raw[start : start + count * components].reshape(count, components)
    else:
        offsets = start + np.arange(count)[:, None] * stride + np.arange(components)[None, :]
        values = raw[offsets]

    rgb = values[:, :3].astype(np.float32) / 255.0
    if convert_srgb:
        rgb = _srgb_to_linear(rgb)

    rgba = np.ones((count, 4), dtype=np.float32)
    rgba[:, :3] = rgb
    if components == 4:
        rgba[:, 3] = values[:, 3].astype(np.float32) / 255.0
    return rgba


def _build_display_material(attribute_name: str) -> bpy.types.Material:
    material_name = "PointCloud_GLTF_Color"
    material = bpy.data.materials.get(material_name) or bpy.data.materials.new(material_name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()

    attribute = nodes.new("ShaderNodeAttribute")
    attribute.attribute_name = attribute_name
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Strength"].default_value = 1.0
    output = nodes.new("ShaderNodeOutputMaterial")
    material.node_tree.links.new(attribute.outputs["Color"], emission.inputs["Color"])
    material.node_tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return material


def _build_geometry_nodes(material: bpy.types.Material) -> bpy.types.NodeTree:
    group_name = "PointCloud_GLTF_Color_Display"
    group = bpy.data.node_groups.get(group_name)
    if group is None:
        group = bpy.data.node_groups.new(group_name, "GeometryNodeTree")
    else:
        group.nodes.clear()
        for item in list(group.interface.items_tree):
            if item.item_type == "SOCKET":
                group.interface.remove(item)

    group.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    group.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    group_input = group.nodes.new("NodeGroupInput")
    set_material = group.nodes.new("GeometryNodeSetMaterial")
    set_material.inputs["Material"].default_value = material
    group_output = group.nodes.new("NodeGroupOutput")
    group.links.new(group_input.outputs["Geometry"], set_material.inputs["Geometry"])
    group.links.new(set_material.outputs["Geometry"], group_output.inputs["Geometry"])
    return group


def restore_glb_point_colors(
    glb_path: str,
    object_name: str = "geometry_0",
    mesh_index: int = 0,
    primitive_index: int = 0,
    attribute_name: str = "color",
    convert_srgb: bool = True,
) -> dict:
    path = Path(glb_path)
    if not path.is_file():
        raise FileNotFoundError(path)

    obj = bpy.data.objects.get(object_name)
    if obj is None or obj.type != "POINTCLOUD":
        raise RuntimeError(f"{object_name!r} is not a Blender POINTCLOUD object")

    document, binary = _read_glb(path)
    colors = _decode_color_0(document, binary, mesh_index, primitive_index, convert_srgb)
    point_count = len(obj.data.points)
    if len(colors) != point_count:
        raise RuntimeError(f"Point count mismatch: GLB {len(colors)} vs Blender {point_count}")

    existing = obj.data.attributes.get(attribute_name)
    if existing is not None:
        obj.data.attributes.remove(existing)
    attribute = obj.data.attributes.new(attribute_name, "FLOAT_COLOR", "POINT")
    attribute.data.foreach_set("color", colors.ravel())

    material = _build_display_material(attribute_name)
    node_group = _build_geometry_nodes(material)
    modifier = obj.modifiers.get("GLTF Point Color") or obj.modifiers.new("GLTF Point Color", "NODES")
    modifier.node_group = node_group

    scene = bpy.context.scene
    scene.display_settings.display_device = "sRGB"
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0
    if scene.world is None:
        scene.world = bpy.data.worlds.new("World")
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    if background is not None:
        background.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
        background.inputs["Strength"].default_value = 0.0

    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                shading = area.spaces.active.shading
                shading.type = "RENDERED"
                shading.use_scene_world_render = True
                shading.use_scene_lights_render = False
                area.tag_redraw()

    return {
        "object": obj.name,
        "points": point_count,
        "attribute": attribute.name,
        "material": material.name,
        "modifier": modifier.name,
        "converted_srgb": convert_srgb,
        "saved": False,
    }


def _parse_args() -> argparse.Namespace:
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--glb", required=True)
    parser.add_argument("--object", default="geometry_0")
    parser.add_argument("--mesh-index", type=int, default=0)
    parser.add_argument("--primitive-index", type=int, default=0)
    parser.add_argument("--attribute", default="color")
    parser.add_argument("--linear-input", action="store_true", help="Do not convert RGB from sRGB to linear")
    return parser.parse_args(arguments)


if __name__ == "__main__":
    args = _parse_args()
    result = restore_glb_point_colors(
        glb_path=args.glb,
        object_name=args.object,
        mesh_index=args.mesh_index,
        primitive_index=args.primitive_index,
        attribute_name=args.attribute,
        convert_srgb=not args.linear_input,
    )
    print(json.dumps(result, ensure_ascii=False))
