"""One-click importer for DA3 GLB point clouds with faithful colors."""

from __future__ import annotations

import json
import struct
import traceback
from pathlib import Path

import bpy
import numpy as np
from bpy.props import BoolProperty, FloatProperty, StringProperty
from bpy_extras.io_utils import ImportHelper


bl_info = {
    "name": "DA3 Colored GLB Importer",
    "author": "Purextreme",
    "version": (0, 2, 0),
    "blender": (5, 2, 0),
    "location": "File > Import > DA3 Colored Point Cloud (.glb)",
    "description": "Import DA3 GLB point clouds and restore COLOR_0 as unlit color",
    "category": "Import-Export",
}


ATTRIBUTE_NAME = "color"
MATERIAL_TAG = "da3_glb_importer_material"
NODE_GROUP_TAG = "da3_glb_importer_node_group"
NODE_GROUP_VERSION_TAG = "da3_glb_importer_node_group_version"
NODE_GROUP_VERSION = 3


def _read_glb(path: Path) -> tuple[dict, bytes]:
    with path.open("rb") as handle:
        header = handle.read(12)
        if len(header) != 12:
            raise RuntimeError("文件不是有效的 GLB")
        magic, version, total_length = struct.unpack("<4sII", header)
        if magic != b"glTF" or version != 2:
            raise RuntimeError("仅支持 GLB 2.0 文件")

        document = None
        binary = None
        while handle.tell() < total_length:
            chunk_header = handle.read(8)
            if len(chunk_header) != 8:
                raise RuntimeError("GLB 数据块不完整")
            chunk_length, chunk_type = struct.unpack("<II", chunk_header)
            chunk = handle.read(chunk_length)
            if len(chunk) != chunk_length:
                raise RuntimeError("GLB 数据块长度不匹配")
            if chunk_type == 0x4E4F534A:
                document = json.loads(chunk.decode("utf-8").rstrip("\x00 "))
            elif chunk_type == 0x004E4942:
                binary = chunk

    if document is None or binary is None:
        raise RuntimeError("GLB 必须同时包含 JSON 和 BIN 数据块")
    return document, binary


def _point_specs(document: dict) -> list[dict]:
    specs = []
    nodes = document.get("nodes", [])
    for mesh_index, mesh in enumerate(document.get("meshes", [])):
        hints = {mesh.get("name", "")}
        hints.update(node.get("name", "") for node in nodes if node.get("mesh") == mesh_index)
        hints.discard("")

        for primitive_index, primitive in enumerate(mesh.get("primitives", [])):
            if primitive.get("mode", 4) != 0:
                continue
            color_accessor_index = primitive.get("attributes", {}).get("COLOR_0")
            if color_accessor_index is None:
                continue
            accessor = document["accessors"][color_accessor_index]
            specs.append(
                {
                    "mesh_index": mesh_index,
                    "primitive_index": primitive_index,
                    "count": accessor["count"],
                    "hints": hints,
                }
            )

    if not specs:
        raise RuntimeError("没有找到同时包含 POINTS 和 COLOR_0 的 DA3 点云")
    return specs


def _srgb_to_linear(rgb: np.ndarray) -> np.ndarray:
    return np.where(
        rgb <= 0.04045,
        rgb / 12.92,
        ((rgb + 0.055) / 1.055) ** 2.4,
    ).astype(np.float32)


def _decode_color_0(document: dict, binary: bytes, spec: dict) -> np.ndarray:
    primitive = document["meshes"][spec["mesh_index"]]["primitives"][spec["primitive_index"]]
    accessor = document["accessors"][primitive["attributes"]["COLOR_0"]]
    if accessor.get("componentType") != 5121 or not accessor.get("normalized", False):
        raise RuntimeError("DA3 COLOR_0 必须是 normalized unsigned byte")

    components = {"VEC3": 3, "VEC4": 4}.get(accessor.get("type"))
    if components is None:
        raise RuntimeError("DA3 COLOR_0 仅支持 VEC3 或 VEC4")
    if "bufferView" not in accessor:
        raise RuntimeError("暂不支持 sparse COLOR_0 accessor")

    view = document["bufferViews"][accessor["bufferView"]]
    count = accessor["count"]
    start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    stride = view.get("byteStride", components)
    if stride < components:
        raise RuntimeError("COLOR_0 byteStride 无效")

    raw = np.frombuffer(binary, dtype=np.uint8)
    last_byte = start + (count - 1) * stride + components if count else start
    if start < 0 or last_byte > len(raw):
        raise RuntimeError("COLOR_0 accessor 超出 GLB BIN 数据范围")

    if stride == components:
        values = raw[start : start + count * components].reshape(count, components)
    else:
        offsets = start + np.arange(count)[:, None] * stride + np.arange(components)[None, :]
        values = raw[offsets]

    rgba = np.ones((count, 4), dtype=np.float32)
    rgba[:, :3] = _srgb_to_linear(values[:, :3].astype(np.float32) / 255.0)
    if components == 4:
        rgba[:, 3] = values[:, 3].astype(np.float32) / 255.0
    return rgba


def _base_name(name: str) -> str:
    head, separator, suffix = name.rpartition(".")
    return head if separator and len(suffix) == 3 and suffix.isdigit() else name


def _match_point_objects(specs: list[dict], new_objects: list[bpy.types.Object]) -> list[tuple[dict, bpy.types.Object]]:
    remaining = [obj for obj in new_objects if obj.type == "POINTCLOUD"]
    matches = []

    for spec in specs:
        candidates = [obj for obj in remaining if len(obj.data.points) == spec["count"]]
        if len(candidates) > 1 and spec["hints"]:
            hinted = [obj for obj in candidates if _base_name(obj.name) in spec["hints"]]
            if len(hinted) == 1:
                candidates = hinted
        if len(candidates) != 1:
            names = ", ".join(obj.name for obj in candidates) or "无"
            raise RuntimeError(
                f"无法唯一匹配 mesh {spec['mesh_index']} primitive {spec['primitive_index']} "
                f"({spec['count']} 点)；候选对象：{names}"
            )
        obj = candidates[0]
        remaining.remove(obj)
        matches.append((spec, obj))
    return matches


def _tagged_material() -> bpy.types.Material:
    for material in bpy.data.materials:
        if material.get(MATERIAL_TAG):
            return material

    material = bpy.data.materials.new("DA3 Point Color")
    material[MATERIAL_TAG] = True
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    attribute = nodes.new("ShaderNodeAttribute")
    attribute.attribute_name = ATTRIBUTE_NAME
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Strength"].default_value = 1.0
    output = nodes.new("ShaderNodeOutputMaterial")
    material.node_tree.links.new(attribute.outputs["Color"], emission.inputs["Color"])
    material.node_tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return material


def _tagged_node_group(material: bpy.types.Material) -> bpy.types.NodeTree:
    group = None
    for candidate in bpy.data.node_groups:
        if candidate.bl_idname == "GeometryNodeTree" and candidate.get(NODE_GROUP_TAG):
            if candidate.get(NODE_GROUP_VERSION_TAG) == NODE_GROUP_VERSION:
                return candidate
            group = candidate
            break

    if group is None:
        group = bpy.data.node_groups.new("DA3 Point Color Display", "GeometryNodeTree")
    else:
        group.nodes.clear()
        group.interface.clear()

    group[NODE_GROUP_TAG] = True
    group[NODE_GROUP_VERSION_TAG] = NODE_GROUP_VERSION
    group.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    override_radius = group.interface.new_socket(
        name="Override Point Radius",
        in_out="INPUT",
        socket_type="NodeSocketBool",
    )
    override_radius.default_value = False
    point_radius = group.interface.new_socket(
        name="Point Radius",
        in_out="INPUT",
        socket_type="NodeSocketFloat",
    )
    point_radius.default_value = 0.01
    point_radius.min_value = 0.0
    point_radius.max_value = 1000.0
    group.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    group_input = group.nodes.new("NodeGroupInput")
    set_radius = group.nodes.new("GeometryNodeSetPointRadius")
    geometry_switch = group.nodes.new("GeometryNodeSwitch")
    geometry_switch.input_type = "GEOMETRY"
    set_material = group.nodes.new("GeometryNodeSetMaterial")
    set_material.inputs["Material"].default_value = material
    group_output = group.nodes.new("NodeGroupOutput")
    group.links.new(group_input.outputs["Geometry"], set_radius.inputs["Points"])
    group.links.new(group_input.outputs["Point Radius"], set_radius.inputs["Radius"])
    group.links.new(group_input.outputs["Geometry"], geometry_switch.inputs["False"])
    group.links.new(set_radius.outputs["Points"], geometry_switch.inputs["True"])
    group.links.new(group_input.outputs["Override Point Radius"], geometry_switch.inputs["Switch"])
    group.links.new(geometry_switch.outputs["Output"], set_material.inputs["Geometry"])
    group.links.new(set_material.outputs["Geometry"], group_output.inputs["Geometry"])
    return group


def _input_socket(node_group: bpy.types.NodeTree, name: str):
    for item in node_group.interface.items_tree:
        if item.item_type == "SOCKET" and item.in_out == "INPUT" and item.name == name:
            return item
    raise RuntimeError(f"Geometry Nodes 缺少输入：{name}")


def _set_modifier_input(modifier: bpy.types.NodesModifier, socket, value) -> None:
    getattr(modifier.properties.inputs, socket.identifier).value = value


def _apply_colors(
    obj: bpy.types.Object,
    colors: np.ndarray,
    node_group: bpy.types.NodeTree,
    override_point_radius: bool,
    point_radius: float,
) -> None:
    point_count = len(obj.data.points)
    if len(colors) != point_count:
        raise RuntimeError(f"点数不匹配：GLB {len(colors)}，Blender {point_count}")

    existing = obj.data.attributes.get(ATTRIBUTE_NAME)
    if existing is not None:
        obj.data.attributes.remove(existing)
    attribute = obj.data.attributes.new(ATTRIBUTE_NAME, "FLOAT_COLOR", "POINT")
    attribute.data.foreach_set("color", colors.ravel())
    modifier = obj.modifiers.get("DA3 Point Color") or obj.modifiers.new("DA3 Point Color", "NODES")
    modifier.node_group = node_group
    _set_modifier_input(modifier, _input_socket(node_group, "Override Point Radius"), override_point_radius)
    _set_modifier_input(modifier, _input_socket(node_group, "Point Radius"), point_radius)


def _configure_display(scene: bpy.types.Scene) -> None:
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


def _remove_imported_objects(objects: list[bpy.types.Object]) -> None:
    for obj in objects:
        if obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)


class IMPORT_SCENE_OT_da3_colored_glb(bpy.types.Operator, ImportHelper):
    bl_idname = "import_scene.da3_colored_glb"
    bl_label = "DA3 Colored Point Cloud (.glb)"
    bl_description = "Import a DA3 GLB and restore point colors as unlit emission"
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = ".glb"
    filter_glob: StringProperty(default="*.glb", options={"HIDDEN"})
    override_point_radius: BoolProperty(
        name="Override Point Radius",
        description="Override the native point radius with one uniform value",
        default=False,
    )
    point_radius: FloatProperty(
        name="Point Radius",
        description="Uniform point radius in scene units when override is enabled",
        default=0.01,
        min=0.0,
        soft_max=1.0,
        subtype="DISTANCE",
        unit="LENGTH",
    )

    def draw(self, _context):
        layout = self.layout
        layout.prop(self, "override_point_radius")
        row = layout.row()
        row.enabled = self.override_point_radius
        row.prop(self, "point_radius")

    def execute(self, context):
        path = Path(self.filepath)
        before_objects = set(bpy.data.objects)
        new_objects = []
        try:
            document, binary = _read_glb(path)
            specs = _point_specs(document)
            result = bpy.ops.import_scene.gltf(
                filepath=str(path),
                import_point_as_pointcloud=True,
                import_select_created_objects=True,
            )
            if "FINISHED" not in result:
                raise RuntimeError("Blender glTF 导入器未能完成导入")

            new_objects = [obj for obj in bpy.data.objects if obj not in before_objects]
            matches = _match_point_objects(specs, new_objects)
            material = _tagged_material()
            node_group = _tagged_node_group(material)
            for spec, obj in matches:
                colors = _decode_color_0(document, binary, spec)
                _apply_colors(
                    obj,
                    colors,
                    node_group,
                    self.override_point_radius,
                    self.point_radius,
                )
            _configure_display(context.scene)

            total_points = sum(spec["count"] for spec, _obj in matches)
            self.report({"INFO"}, f"已导入 {len(matches)} 个 DA3 彩色点云，共 {total_points} 点")
            return {"FINISHED"}
        except Exception as exc:
            imported_objects = new_objects or [obj for obj in bpy.data.objects if obj not in before_objects]
            if imported_objects:
                _remove_imported_objects(imported_objects)
            traceback.print_exc()
            self.report({"ERROR"}, f"DA3 GLB 导入失败：{exc}")
            return {"CANCELLED"}


def _menu_import(self, _context):
    self.layout.operator(IMPORT_SCENE_OT_da3_colored_glb.bl_idname)


classes = (IMPORT_SCENE_OT_da3_colored_glb,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_import.append(_menu_import)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(_menu_import)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
