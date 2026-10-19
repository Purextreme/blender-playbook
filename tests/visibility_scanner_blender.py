"""Run inside interactive Blender. Uses synthetic arrays; does not save or edit models."""

import importlib.util
from pathlib import Path

import bpy
import gpu
import numpy as np

SOURCE = Path(__file__).resolve().parents[1] / 'addons' / 'orange_visibility_scanner' / '__init__.py'
spec = importlib.util.spec_from_file_location('orange_visibility_scanner_test', SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

VERTICES = np.array([[-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
                     [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1]], dtype=np.float32)
TRIANGLES = np.array([[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
                      [0, 1, 5], [0, 5, 4], [3, 7, 6], [3, 6, 2],
                      [0, 4, 7], [0, 7, 3], [1, 2, 6], [1, 6, 5]], dtype=np.int32)


def cube(index, size, offset=(0, 0, 0), transparent=False):
    return {'id': index, 'name': str(index),
            'vertices': VERTICES * size + np.array(offset, dtype=np.float32),
            'triangles': TRIANGLES.copy(), 'transparent': transparent}


def visible_sets(records):
    raster = module.GPUPass(records, 256)
    gpu_ids = set()
    try:
        for direction in module.directions(32):
            counts = raster.draw(direction)
            gpu_ids.update(int(i) for i in np.flatnonzero(counts[1:]) + 1)
    finally:
        raster.close()
    bvh = module.BVHPass(records)
    bvh_ids = {r['id'] for r in records if not r['transparent'] and any(
        bvh.sees(point, direction, r['id']) for point in module.sample_surface(r, 64)
        for direction in module.directions(32))}
    return gpu_ids, bvh_ids


def run():
    counts = {key: len(getattr(bpy.data, key)) for key in ('objects', 'meshes', 'materials', 'collections')}
    projection = gpu.matrix.get_projection_matrix().copy()
    checks = {}
    cases = {
        'enclosed': ([cube(1, .3), cube(2, .1)], {1}),
        'exposed': ([cube(1, .3), cube(2, .1, (.28, 0, 0))], {1, 2}),
        'transparent': ([cube(1, .3, transparent=True), cube(2, .1)], {2}),
    }
    reversed_cube = cube(1, .3)
    reversed_cube['triangles'] = reversed_cube['triangles'][:, ::-1].copy()
    cases['reversed_winding'] = ([reversed_cube, cube(2, .1)], {1})
    for name, (records, expected) in cases.items():
        gpu_ids, bvh_ids = visible_sets(records)
        assert gpu_ids == bvh_ids == expected, (name, gpu_ids, bvh_ids, expected)
        checks[name] = True
    tiny = [cube(1, .3), cube(2, .000001, (.35, .000123, .000456))]
    bvh = module.BVHPass(tiny)
    assert any(bvh.sees(p, d, 2) for p in module.sample_surface(tiny[1], 64) for d in module.directions(32))
    checks['subpixel_bvh_witness'] = True
    assert np.allclose(np.array(projection), np.array(gpu.matrix.get_projection_matrix()))
    checks['gpu_projection_restored'] = True
    if any(o.type == 'MESH' and o.visible_get() and not o.hide_render for o in bpy.context.scene.objects):
        roots = [c.as_pointer() for c in bpy.context.scene.collection.children]
        job = module.ScanJob(bpy.context)
        job.step(.001)
        job.close()
        assert roots == [c.as_pointer() for c in bpy.context.scene.collection.children]
        checks['cancel_preserves_results'] = True
    module.register()
    old_status = bpy.context.scene.vis_scan.status
    module.register()
    assert bpy.context.scene.vis_scan.status == old_status
    checks['repeated_registration'] = True
    assert counts == {key: len(getattr(bpy.data, key)) for key in counts}
    checks['original_datablock_counts'] = True
    return checks


if __name__ == '__main__':
    result = run()
    print(result)
