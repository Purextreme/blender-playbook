"""Camera Material Preview export for Blender 5.2 GUI; no scene-render fallback.

Load with runpy.run_path(), then call run(). See the accompanying operation card.
Only standard Python and bpy are required. Importing this file has no side effects.
"""

import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory


class PrevisError(RuntimeError):
    pass


def _bpy():
    import bpy
    if tuple(bpy.app.version[:2]) != (5, 2):
        raise PrevisError(f"Requires Blender 5.2; found {bpy.app.version_string}")
    if bpy.app.background:
        raise PrevisError("Requires a Blender GUI with a VIEW_3D region; background export is unsupported")
    if not hasattr(bpy.context, "temp_override"):
        raise PrevisError("Missing Context.temp_override")
    required = {"animation", "write_still", "view_context", "sequencer"}
    try:
        supported = set(bpy.ops.render.opengl.get_rna_type().properties.keys())
    except Exception as exc:
        raise PrevisError("Viewport render operator unavailable") from exc
    if not required <= supported:
        raise PrevisError("Unsupported viewport render signature")
    return bpy


def _camera(scene, space):
    return space.camera if space.use_local_camera else scene.camera


def _inventory(bpy):
    rows = []
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type != "VIEW_3D":
                continue
            space = area.spaces.active
            camera = _camera(window.scene, space)
            rows.append({
                "target": {"pid": os.getpid(), "window": str(window.as_pointer()),
                           "area": str(area.as_pointer()), "scene": window.scene.name,
                           "view_layer": window.view_layer.name,
                           "camera": camera.name if camera else None},
                "workspace": window.workspace.name,
                "shading": space.shading.type,
                "perspective": space.region_3d.view_perspective,
            })
    return rows


def _resolve(bpy, target):
    if target.get("pid") != os.getpid():
        raise PrevisError("Target process changed; run check again")
    matches = []
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            if (str(w.as_pointer()) == target.get("window")
                    and str(a.as_pointer()) == target.get("area") and a.type == "VIEW_3D"):
                matches.append((w, a))
    if len(matches) != 1:
        raise PrevisError("Target viewport missing or ambiguous; run check again")
    w, a = matches[0]
    space, scene = a.spaces.active, w.scene
    camera = _camera(scene, space)
    if (scene.name != target.get("scene") or w.view_layer.name != target.get("view_layer")
            or camera is None or camera.type != "CAMERA" or camera.name != target.get("camera")):
        raise PrevisError("Scene, view layer or camera changed; run check again")
    regions = [r for r in a.regions if r.type == "WINDOW"]
    if len(regions) != 1 or space.region_quadviews:
        raise PrevisError("Requires one unambiguous, non-quad VIEW_3D WINDOW region")
    if space.region_3d.view_perspective != "CAMERA" or space.shading.type != "MATERIAL":
        raise PrevisError("Enter the intended camera view and Material Preview before export")
    if space.local_view is not None:
        raise PrevisError("Exit Local View before export to avoid exporting an isolated subset")
    if w.screen.is_animation_playing:
        raise PrevisError("Stop viewport playback before export")
    if bpy.context.mode != "OBJECT":
        raise PrevisError("Enter Object Mode before export")
    if bpy.app.is_job_running("RENDER"):
        raise PrevisError("Another render is running")
    if scene.render.use_multiview:
        raise PrevisError("Stereo/multiview output is not supported by this single-camera exporter")
    # Camera markers can change scene.camera while frame_set() evaluates animation.
    if any(m.camera for m in scene.timeline_markers):
        raise PrevisError("Camera-bound timeline markers are not supported; use a scene without camera cuts")
    return w, a, regions[0], space, scene


def _frames(scene, frame, start, end, step):
    values = [scene.frame_current if frame is None else frame,
              scene.frame_start if start is None else start,
              scene.frame_end if end is None else end, step]
    if any(type(v) is not int for v in values):
        raise PrevisError("Frame, start, end and step must be integers")
    frame, start, end, step = values
    if step < 1 or start > end:
        raise PrevisError("Invalid frame range or step")
    if not (scene.frame_start <= start <= end <= scene.frame_end
            and scene.frame_start <= frame <= scene.frame_end):
        raise PrevisError("Requested frames must be within the scene frame range")
    return frame, start, end, step


def _output(output_dir):
    if not output_dir:
        raise PrevisError("An absolute, new output_dir is required")
    path = Path(output_dir)
    if not path.is_absolute():
        raise PrevisError("output_dir must be absolute (Blender // paths are not accepted)")
    if os.path.lexists(path):
        raise PrevisError(f"Output already exists: {path}")
    if not path.parent.is_dir():
        raise PrevisError(f"Output parent does not exist: {path.parent}")
    return path


def _snapshot(space, scene):
    shading = space.shading
    names = ("studio_light", "studiolight_rotate_z", "studiolight_intensity",
             "studiolight_background_alpha", "studiolight_background_blur",
             "use_studiolight_view_rotation", "use_scene_lights", "use_scene_world")
    return {
        "hdri": {name: getattr(shading, name) for name in names if hasattr(shading, name)},
        "color_management": {name: getattr(scene.view_settings, name)
                             for name in ("view_transform", "look", "exposure", "gamma")},
        "resolution": [scene.render.resolution_x, scene.render.resolution_y,
                       scene.render.resolution_percentage],
        "pixel_aspect": [scene.render.pixel_aspect_x, scene.render.pixel_aspect_y],
        "fps": scene.render.fps / scene.render.fps_base,
    }


def _export(bpy, context, path, frames):
    window, area, region, space, scene = context
    original_frame = (scene.frame_current, scene.frame_subframe)
    written = []
    image = scene.render.image_settings
    settings = [
        (space.shading, "use_scene_lights", False),
        (space.shading, "use_scene_world", False),
        (space.overlay, "show_overlays", False),
        (space, "show_gizmo", False),
        (scene.render, "filepath", str(path / "unused")),
        (scene.render, "use_file_extension", True),
        (scene.render, "use_overwrite", False),
        (scene.render, "use_placeholder", False),
        (image, "media_type", "IMAGE"),
        (image, "file_format", "PNG"),
        (image, "color_mode", "RGBA"),
        (image, "color_depth", "8"),
        (image, "color_management", "FOLLOW_SCENE"),
    ]
    # Read all originals BEFORE changing format: format changes can clamp depth/mode.
    changes = [(obj, key, getattr(obj, key)) for obj, key, value in settings]

    # Atomic exclusive directory creation prevents a preflight-to-write collision.
    path.mkdir(exist_ok=False)
    try:
        for obj, key, value in settings:
            setattr(obj, key, value)
        with bpy.context.temp_override(window=window, area=area, region=region), \
                TemporaryDirectory(prefix=".previs-", dir=path) as scratch:
            if not bpy.ops.render.opengl.poll():
                raise PrevisError("Viewport render poll failed; no scene-render fallback")
            for frame in frames:
                scene.frame_set(frame)
                dest = path / f"frame_{frame:06d}.png"
                temporary = Path(scratch) / "frame.png"
                scene.render.filepath = str(temporary)
                result = bpy.ops.render.opengl("EXEC_DEFAULT", animation=False,
                                              write_still=True, view_context=True, sequencer=False)
                if result != {"FINISHED"}:
                    raise PrevisError(f"Viewport render did not finish at frame {frame}: {result}")
                with temporary.open("rb") as stream:
                    if stream.read(8) != b"\x89PNG\r\n\x1a\n":
                        raise PrevisError(f"No valid PNG written at frame {frame}")
                    stream.seek(0)
                    # Exclusive publication never replaces an existing destination.
                    with dest.open("xb") as output:
                        shutil.copyfileobj(stream, output)
                temporary.unlink()
                written.append(str(dest))
    finally:
        # EXEC_DEFAULT finishes synchronously, so restoration cannot race a modal job.
        errors = []
        try:
            scene.frame_set(original_frame[0], subframe=original_frame[1])
        except Exception as exc:
            errors.append(f"frame: {exc}")
        # Restore media type and format BEFORE mode/depth (e.g. EXR 32-bit).
        for obj, key, value in changes:
            try:
                setattr(obj, key, value)
            except Exception as exc:
                errors.append(f"{key}: {exc}")
        if errors:
            raise PrevisError("Restoration incomplete: " + "; ".join(errors))
    return written


def run(mode="check", *, target=None, output_dir=None, frame=None,
        start=None, end=None, step=1):
    """Return JSON-compatible inspection/export results; raise on any unsafe state.

    check without target lists viewports. check with target validates a full export
    request without changing Blender or creating files. sample exports one frame;
    animation exports start..end inclusively with step, as PNG files.
    """
    if mode not in {"check", "sample", "animation"}:
        raise PrevisError("mode must be check, sample or animation")
    bpy = _bpy()
    if target is None:
        if mode != "check":
            raise PrevisError("Explicit target from check is required")
        rows = _inventory(bpy)
        if not rows:
            raise PrevisError("No usable VIEW_3D window found")
        return {"version": bpy.app.version_string, "ready": False, "viewports": rows}
    context = _resolve(bpy, target)
    scene = context[-1]
    frame, start, end, step = _frames(scene, frame, start, end, step)
    path = _output(output_dir)
    with bpy.context.temp_override(window=context[0], area=context[1], region=context[2]):
        if not bpy.ops.render.opengl.poll():
            raise PrevisError("Viewport render poll failed")
    report = {"version": bpy.app.version_string, "ready": True, "target": dict(target),
              "output_dir": str(path), "sample_frame": frame, "range": [start, end, step],
              "settings": _snapshot(context[3], scene),
              "export_overrides": {"scene_lights": False, "scene_world": False,
                                   "overlays": False, "format": "PNG RGBA 8-bit"},
              "write_access": "not tested by check; execution creates a new directory"}
    if mode != "check":
        frames = [frame] if mode == "sample" else range(start, end + 1, step)
        report["files"] = _export(bpy, context, path, frames)
    return report
