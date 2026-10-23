# Camera Material Preview export (Blender 5.2)

## Scope and status

Use [../scripts/export_material_preview.py](../scripts/export_material_preview.py) for camera-view Material Preview stills and PNG animation sequences in an existing Blender **5.2 GUI**. It uses the built-in viewport render operator, not regular scene rendering. No external packages are needed.

Target: Blender 5.2.x only. Blender 5.2.2 LTS passed a real GUI sample export and a two-frame sequence in a disposable default scene; the sample PNG was opened successfully. RNA, headless rejection and state restoration were also checked with a simulated render operator. **Actual Esc cancellation and visual equivalence for the user's scene have not been verified.** Do not describe a scene's appearance as validated until the sample comparison below passes.

## Procedure

1. Verify the intended Blender process/connection. Read the script before executing it. Use a GUI connection executing Python on Blender's main thread; do not invoke this export via `blender --background` or a background-only MCP tool.
2. In the intended viewport, enter Object Mode, select the intended camera view and Material Preview, and stop playback. Preserve the existing studio HDRI, rotation, intensity and background settings. Leave Local View and quad view. The minimal exporter rejects stereo/multiview output and camera-bound timeline markers; it does not rewrite camera cuts.
3. Load the script and inventory the actual windows. Select a target based on the intended window, workspace, scene, view layer and camera; do not blindly choose the first viewport. Pointer IDs are session-local: rerun inspection after changing windows or restarting Blender.

```python
import runpy
api = runpy.run_path(r"C:\Users\6730\.codex\skills\blender-playbook\scripts\export_material_preview.py")
print(api["run"]("check"))
```

4. Copy the complete `target` dictionary from the intended inventory entry. Supply an absolute **nonexistent directory** whose parent already exists. `check` reports settings and validates the target, frame range and destination without changing Blender or creating files. Actual filesystem write permission is checked when export creates the directory.

```python
target = {...}  # exact returned pid/window/area/scene/view_layer/camera dictionary
print(api["run"]("check", target=target,
                 output_dir=r"D:\previs\sample_001", frame=12,
                 start=1, end=48, step=1))
print(api["run"]("sample", target=target,
                 output_dir=r"D:\previs\sample_001", frame=12))
```

5. Compare that PNG against the same camera frame in Material Preview, with Scene Lights and Scene World disabled and overlays hidden. Match camera crop/aspect, color management and HDRI; inspect material colors, reflections, highlights, transparency and background. View both through a consistent color-managed display. A viewport screenshot can have different dimensions and sampling, so pixel identity is not assumed. Restore any manual comparison changes afterward. Resolve any visible mismatch before exporting a full sequence.
6. Use a **different new directory** for the animation. The inclusive start/end and step must lie within the scene's frame range. Output uses the scene's resolution, percentage and pixel aspect. Files are `frame_000001.png`, etc.; the script does not encode video. With step > 1, account for the reported scene FPS and skipped frames when encoding externally.

```python
print(api["run"]("check", target=target,
                 output_dir=r"D:\previs\animation_001", start=1, end=48))
print(api["run"]("animation", target=target,
                 output_dir=r"D:\previs\animation_001", start=1, end=48))
```

## Preservation and failure behavior

- The exporter requires an explicit, unchanged target and an already configured camera Material Preview. It never guesses a viewport, changes cameras, creates scene lighting or falls back to `bpy.ops.render.render`.
- Studio HDRI selection, rotation, intensity, background and scene color management are preserved. Scene Lights/World, overlays and gizmos are temporarily disabled. Output temporarily becomes PNG RGBA 8-bit with scene color management.
- Synchronous per-frame `EXEC_DEFAULT` calls keep restoration in `finally` after rendering has finished. The original frame/subframe, output settings and changed viewport properties are restored on success, exceptions and Python interruption. A returned `CANCELLED` is treated as failure. Restoration errors are surfaced explicitly.
- Existing directories are refused; each final PNG is created exclusively, so collisions stop the job without overwriting the existing file. Successful earlier frames and any partial final file remain on failure; inspect them and use a new directory for a retry. Do not retry an unknown-completion operation automatically.
- The script does not save the blend file or edit models, materials, lights or animation data. Frame evaluation can run existing scene handlers/simulations; it cannot reverse arbitrary side effects of third-party handlers. Blender process termination or a GPU/process crash cannot run Python cleanup.

## Verification

Before marking GUI support verified on a particular build, export a sample and a short range, compare the sample as above, and confirm that the original frame/subframe, HDRI, overlays and output settings return after success, an injected render failure and cancellation. Also verify that an existing output directory is rejected without changing its contents. A functioning API and passing simulated tests do not prove visual equivalence.

References: [Blender 5.2 render API](https://docs.blender.org/api/5.2/bpy.ops.render.html), [Viewport Render manual](https://docs.blender.org/manual/en/5.2/editors/3dview/viewport_render.html).
