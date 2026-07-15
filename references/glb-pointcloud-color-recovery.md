# Recover GLB point-cloud colors

## Applicability

Use when a `.glb` or `.gltf` looks colored in its source viewer but imports into Blender as a gray `POINTCLOUD`, especially when the source contains a `POINTS` primitive.

## Core conclusions

- A valid GLB can contain color without textures. Per-point color normally appears as primitive attribute `COLOR_0`.
- Blender may import a glTF `mode: 0` (`POINTS`) primitive as `POINTCLOUD` while retaining only `position` and dropping `COLOR_0`.
- Inspect the GLB JSON and accessors before changing materials. Missing textures are irrelevant when the file has no images and uses vertex colors.
- Require exact equality between the GLB color accessor count and Blender point count. Stop on any mismatch.

## Diagnostic procedure

1. Read the GLB header and JSON chunk without modifying Blender.
2. Identify the target mesh primitive and confirm `mode == 0`.
3. Confirm `attributes.COLOR_0` exists.
4. Inspect its accessor: component type, vector type, normalized flag, count, buffer view, offsets, and byte stride.
5. Inspect the imported Blender object type and attributes.
6. Compare the accessor count with `len(object.data.points)`.

For the verified case, the source used normalized unsigned-byte `VEC4` colors (`componentType: 5121`) and one million points. Blender 5.2.0 LTS imported the object with only a `position` attribute.

## Recovery procedure

Use [../scripts/restore_glb_point_colors.py](../scripts/restore_glb_point_colors.py) for the supported normalized unsigned-byte `VEC3`/`VEC4` case.

The script must:

1. Parse the GLB JSON and BIN chunks.
2. Resolve accessor and buffer-view offsets, including `byteStride`.
3. Decode `COLOR_0` without reordering points.
4. Convert RGB from sRGB to linear before shader use when the bytes originate from display imagery.
5. Create a point-domain `FLOAT_COLOR` attribute named `color`.
6. Create an emission material and Geometry Nodes pass-through that applies it to the point cloud.
7. Configure a black world and a predictable Standard display transform.

## Decision points

- Do not assume primitive index zero for unrelated files; inspect mesh and primitive structure first.
- Do not apply the sRGB-to-linear conversion blindly to scientifically linear color data. Establish how the exporter encoded `COLOR_0`.
- If the imported object is a mesh rather than a point cloud, prefer Blender's native color-attribute/material path instead of adding this point-cloud Geometry Nodes setup.
- If the accessor format is unsupported by the bundled script, extend it deliberately and test on a copy rather than coercing the data.

## Common pitfalls

- Changing viewport shading cannot recover an attribute that was never imported.
- A `POINTCLOUD` object does not expose ordinary material slots like a mesh.
- Writing raw sRGB bytes directly as linear shader values makes dark imagery too bright and washed out.
- Workbench vertex-color display is not a reliable final color reference for point clouds.
- Never silently continue after a point-count mismatch.

## Verification

- Confirm the recovered attribute domain is `POINT` and its length equals the point count.
- Sample first, middle, and last colors after writing.
- Confirm the Geometry Nodes modifier and emission material exist.
- Disable scene lights; appearance should remain unchanged.
- Compare a Rendered viewport screenshot with the source reference image.
- Report whether the `.blend` remains unsaved.

## Provenance

Verified on Blender 5.2.0 LTS with a Trimesh-generated GLB containing one million colored points and forty colored line primitives.
