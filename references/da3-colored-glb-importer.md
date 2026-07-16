# DA3 colored GLB importer

## Applicability

Use when DA3 exports a GLB containing a glTF `POINTS` primitive with image-derived `COLOR_0`, and repeated manual color recovery in Blender is no longer desirable.

## Core conclusions

- The dedicated importer is available at `File > Import > DA3 Colored Point Cloud (.glb)`.
- It deliberately enables Blender's `Import Points as Point Cloud` option so the main DA3 primitive becomes a native `POINTCLOUD` object.
- DA3 stores image-derived colors as normalized unsigned-byte `COLOR_0`; decode RGB as sRGB and store shader-facing values in Linear space.
- Keep the import deterministic: exact point-count equality and unique object matching are hard requirements.
- Display recovered color through Emission strength `1.0`; scene lights must not affect the result.

## Why Import Points as Point Cloud is enabled

On Blender 5.2.0 LTS, disabling the option imported a verified 406,425-point DA3 primitive as a `MESH` containing 406,425 loose vertices, zero edges, and zero polygons. Its `Color` attribute existed, but loose vertices are not a directly renderable point-cloud surface.

Enabling the option imported the same primitive as native `POINTCLOUD`, which is the intended data type for the Geometry Nodes and Emission display workflow. Blender dropped `COLOR_0` in this mode, so the add-on restores it from the original GLB bytes.

## Installation and use

The source is in [`../addons/da3_glb_importer`](../addons/da3_glb_importer). Install [`../dist/da3_glb_importer-0.2.0.zip`](../dist/da3_glb_importer-0.2.0.zip) through Blender Preferences and enable `DA3 Colored GLB Importer`.

Import through the dedicated menu entry rather than Blender's standard glTF entry. The add-on automatically:

1. Parses the GLB and locates colored `POINTS` primitives.
2. Calls Blender's glTF importer with `import_point_as_pointcloud=True`.
3. Matches newly imported point clouds by exact point count and source name hints.
4. Restores a point-domain `FLOAT_COLOR` attribute named `color`.
5. Converts sRGB RGB values to Linear and preserves alpha.
6. Applies a shared Emission material through Geometry Nodes.
7. Configures Standard/sRGB display, a black World, and a rendered viewport that ignores scene lights.

`Override Point Radius` is disabled by default, so the Geometry Nodes modifier preserves Blender's native point radius. Enable it to apply the uniform `Point Radius` value. Both controls remain exposed on the object's `DA3 Point Color` modifier after import.

## Failure behavior

- Stop if no colored `POINTS` primitive exists.
- Stop for unsupported `COLOR_0` encodings.
- Stop if the GLB color count and Blender point count differ.
- Stop when more than one newly imported object could match the same primitive.
- Remove objects created by a failed add-on import rather than leaving a partial result.

## Verification

Verified on Blender 5.2.0 LTS with:

- `scene (2).glb`: 406,425 point colors restored exactly; rendered color output confirmed without lights.
- `scene (1).glb`: 1,000,000 point colors restored exactly; repeat import and shared resource reuse confirmed.
- Radius override disabled: native `0.01` radius passed through without creating a `radius` attribute.
- Radius override enabled at `0.025`: evaluated point radius and `radius` attribute both matched `0.025`.

The `.blend` used for testing remained unsaved.
