---
name: blender-playbook
description: Personal Blender experience library for reusable workflows, scene operations, modeling, materials, Geometry Nodes, import/export, color management, rendering, automation, diagnostics, and verified fixes. Use whenever Codex works in Blender, operates Blender through MCP or Python, handles .blend/.glb/.gltf files, or should apply the user's accumulated Blender practices and skill cards.
---

# Blender Playbook

Apply the user's verified Blender practices before improvising. Keep this file concise; load only the reference card relevant to the current task.

## Core workflow

1. Select and verify the target Blender instance using the instance rule below, then inspect its live version, active scene, target objects, data types, attributes, materials, modifiers, render engine, and color-management state before mutation.
2. Route the request to the closest card below and read it completely.
3. Prefer a bundled script when the card identifies one. Read the script before adapting or sending it to Blender.
4. Make the smallest scoped change. Do not overwrite source assets or save an unsaved `.blend` unless the user requests it.
5. Treat topology, point-count, attribute-length, and object-identity mismatches as hard stops.
6. Verify with Blender-side inspection and, when visual output matters, a viewport screenshot or render.
7. Report what changed, what was verified, Blender version, and whether the scene was saved.

## Card routing

- For GLB/GLTF point clouds that lose vertex colors on import, read [references/glb-pointcloud-color-recovery.md](references/glb-pointcloud-color-recovery.md).
- For vertex or point colors that must match source imagery without lighting, read [references/unlit-attribute-color.md](references/unlit-attribute-color.md).
- For installing or using the one-click DA3 colored GLB importer, read [references/da3-colored-glb-importer.md](references/da3-colored-glb-importer.md).
- For detecting externally visible objects and interior candidates without deleting geometry, use the 🍊 Visibility Scanner and read [references/object-visibility-scanner.md](references/object-visibility-scanner.md).

## Personal operating principles

- **Target instance:** Operate the user's foreground Blender instance by default. If the user asks for a new or separate Blender instance, launch and work in that instance. The new instance may be GUI-based or background/headless; unless the user specifies a mode, choose whichever is most practical for automation while supporting the required output and visual verification. Verify the target process/session and script invocation or automation connection before any scene mutation; an existing MCP connection may still target the original instance. If the new instance cannot be targeted reliably, resolve the connection or report the blocker; do not fall back to modifying the original instance.
- **Continuous product-animation motion:** Unless the user explicitly requests a pause or stop, keep each intended camera, product, or light motion moving throughout its shot, including the first and last delivered frames. Slow motion is allowed; unintended zero speed or a visually frozen interval is not. This means nonzero motion speed, not positive acceleration: speed may stay constant, increase, or decrease. Static objects and individual constant transform channels need not move. Avoid ease-in/ease-out curves that reach zero speed within the delivered range. Use linear interpolation, suitable nonzero curve tangents, or extend the motion beyond the export range and trim to a continuously moving segment. Check evaluated motion near both endpoints and internal keys, and inspect playback in the delivery view for unintended stops; tiny numerical changes alone do not establish visible motion.
- **Previs appearance and output:** When the user asks for Blender previs, use the camera-view Material Preview appearance as the default visual target and capture/export that viewport appearance. Use its studio HDRI with Scene Lights and Scene World disabled, avoiding a custom lighting or world setup solely for previs. Material Preview is a viewport shading mode, not a separate render engine; do not substitute a regular Eevee scene render and assume it matches. Verify an exported sample against the Material Preview camera view. If the available export path cannot preserve that appearance, resolve the capture method or explain the limitation before changing the visual target. Explicit user requests for another shading mode or render engine take precedence.

- For personal custom Blender add-ons, preserve the original user-facing names and prepend exactly one `🍊 ` (emoji plus a space) to the add-on name, panel title and sidebar tab. For example, `Visibility` becomes `🍊 Visibility`. Do not add the word `橘子`, otherwise rename the original text, or duplicate an existing prefix. Keep technical module/package names and operator IDs unchanged.
- **Available asset library:** The user has installed the Poly Haven add-on/resource pack. When models or textures are needed, inspect and reuse suitable assets from that library as appropriate. Verify actual asset availability and file paths in the target Blender instance, including when using a new or headless instance.
- Preserve the original asset and existing user work.
- Diagnose from actual Blender state and source-file structure, not appearance alone.
- Separate import fidelity, shader interpretation, color management, and viewport mode; each can independently change the result.
- Prefer deterministic scripts for fragile binary parsing or million-element attribute writes.
- Keep named resources idempotent so a verified operation can be rerun safely.
- Do not add speculative options or broad scene cleanup.

## Adding experience

Add a card only after a real task has produced evidence and a verified result. Each card should include applicability, core conclusions, procedure, decision points, pitfalls, verification, reusable resources, and tested versions. Put deterministic repeated code in `scripts/` and link it directly from the card and this file when it becomes a common route.
