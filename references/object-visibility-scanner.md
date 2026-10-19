# 🍊 Object visibility scanner

## Applicability

Use for product/CAD assembly cleanup when the user wants objects classified by external visibility, preserving original geometry and hierarchy. This is object-level candidate detection, not an interior-face cleanup or a proof that an object can be safely deleted.

## Reusable resources

- Source: [`../addons/orange_visibility_scanner/__init__.py`](../addons/orange_visibility_scanner/__init__.py).
- Installation ZIP: [`../dist/orange_visibility_scanner-1.0.2.zip`](../dist/orange_visibility_scanner-1.0.2.zip).
- User instructions: [`../addons/orange_visibility_scanner/README.md`](../addons/orange_visibility_scanner/README.md).
- Blender regression tests: [`../tests/visibility_scanner_blender.py`](../tests/visibility_scanner_blender.py).
- Build with `python scripts/build_visibility_scanner.py` from the repository root.

## Core conclusions and decision points

- Prefer the existing `🍊 Visibility Scanner - Object Classification` over rewriting a scene-specific scanner. The sidebar is `N > 🍊 Visibility`; the operator is `bpy.ops.object.visibility_scan('EXEC_DEFAULT')`.
- Default to GPU ID plus BVH rechecking. Direct GPU rasterization avoids full-render startup and material changes; BVH rays can find visible surfaces too small to cover a pixel. Neither method guarantees complete coverage with finite samples.
- Compare methods on the actual geometry before claiming one is faster. Higher GPU resolution increases framebuffer/readback cost, while BVH cost grows with directions, surface samples and hidden-object count.
- Read evaluated meshes and normalize world coordinates for numerical stability. Keep original meshes, modifiers, parent links and materials intact.
- Use floating-point IDs without lighting, antialiasing, color management or RGB tolerance. Reject invalid IDs; release GPU resources and restore GPU state after drawing or cancellation.
- Cast BVH rays from outside toward surface samples, rather than offsetting a ray through a potentially thin occluder. Treat a positive hit on the object as evidence to keep the whole object.

## Procedure

1. Inspect the live scene, mode, visibility, render flags, modifiers, material transparency, animation and instancing. Confirm no scan is running before reloading/installing the add-on. Do not save an unsaved scene automatically.
2. Use the visible scene or selected assembly scope. Selected scope includes descendants and uses only that assembly as the occluding geometry. Excluded, hidden or render-disabled objects are skipped.
3. In Object Mode, run the modal operator or create a `ScanJob(context, method='HYBRID', ...)` from the source module. For tool-driven use, step the job until `done`, then call `apply()`; always `close()` on cancellation or failure. A partial scan must never replace results.
4. Classify under `VIS_SCAN_RESULTS`: visible, interior candidates and review. These collections contain additional links, not duplicated meshes or moved objects. Reruns replace only scanner-owned result collections.
5. Review candidates with the panel's select button, then `H` if temporary hiding is useful. Hiding only the result collection may not hide an object also linked to its original collection.
6. For uncertain details, increase directions/resolution/surface samples or use Compare, keeping the union of visible objects. Review transparent, animated, instanced and dependency-bearing objects separately before any later cleanup.
7. Check original object/data counts, geometry, transforms, parents, materials, original collection links, visibility and selection. Report skipped objects, category counts and the current-frame sampling limitation.

## Pitfalls

- Visibility in a finite set of external directions does not cover later camera moves, opened housings, exploded views or indirect rendering contributions.
- Shader node groups are treated conservatively as potentially transparent, even when they are actually opaque; this can leave more objects visible or requiring review.
- Non-mesh/instanced/procedural geometry support is limited. Do not use the candidate set as an automatic deletion list.
- Blender's `Select Interior Faces` is a topology operation and does not detect complete objects enclosed by another object.
- Offscreen GPU drawing requires an interactive Blender GPU context. Do not silently assume background/headless support.

## Verification and tested versions

Verified on Blender 5.2.2 LTS with a real product assembly and synthetic enclosed, partially exposed, transparent-shell, reversed-winding and subpixel-feature cases. Increasing independent GPU and BVH coverage produced the same classification on the tested assembly. Geometry/material/hierarchy preservation, selection, repeated classification, candidate selection, cancellation and GPU projection restoration were checked.

Keep model-specific counts, names and benchmark timings out of reusable defaults. The bundled regression script uses synthetic geometry and no personal media.
