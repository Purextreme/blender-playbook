---
name: blender-playbook
description: Personal Blender experience library for reusable workflows, scene operations, modeling, materials, Geometry Nodes, import/export, color management, rendering, automation, diagnostics, and verified fixes. Use whenever Codex works in Blender, operates Blender through MCP or Python, handles .blend/.glb/.gltf files, or should apply the user's accumulated Blender practices and skill cards.
---

# Blender Playbook

Apply the user's verified Blender practices before improvising. Keep this file concise; load only the reference card relevant to the current task.

## Core workflow

1. Inspect the live Blender version, active scene, target objects, data types, attributes, materials, modifiers, render engine, and color-management state before mutation.
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

- Preserve the original asset and existing user work.
- Diagnose from actual Blender state and source-file structure, not appearance alone.
- Separate import fidelity, shader interpretation, color management, and viewport mode; each can independently change the result.
- Prefer deterministic scripts for fragile binary parsing or million-element attribute writes.
- Keep named resources idempotent so a verified operation can be rerun safely.
- Do not add speculative options or broad scene cleanup.

## Adding experience

Add a card only after a real task has produced evidence and a verified result. Each card should include applicability, core conclusions, procedure, decision points, pitfalls, verification, reusable resources, and tested versions. Put deterministic repeated code in `scripts/` and link it directly from the card and this file when it becomes a common route.
