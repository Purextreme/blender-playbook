bl_info = {
    'name': '🍊 橘子 · Visibility Scanner',
    'author': 'Purextreme',
    'version': (1, 0, 1),
    'blender': (4, 2, 0),
    'location': 'View3D > Sidebar > 🍊 橘子',
    'description': 'Classify visible objects and interior candidates without deleting geometry',
    'category': 'Object',
}

import math
import time
from collections import Counter

import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from bpy.props import BoolProperty, EnumProperty, IntProperty, PointerProperty, StringProperty

OWNER = 'visibility_scanner_v1'
GEOMETRY_TYPES = {'MESH', 'CURVE', 'SURFACE', 'FONT', 'META'}


def directions(count):
    golden = math.pi * (3.0 - math.sqrt(5.0))
    return [Vector((math.cos(i * golden) * math.sqrt(max(0, 1 - y * y)),
                    math.sin(i * golden) * math.sqrt(max(0, 1 - y * y)), y))
            for i in range(count) for y in [1 - 2 * (i + 0.5) / count]]


def transparent_material(mat):
    if mat is None:
        return False
    if mat.diffuse_color[3] < 0.999:
        return True
    if not mat.use_nodes or not mat.node_tree:
        return False
    # Intentionally conservative, including disconnected nodes and driven inputs.
    for node in mat.node_tree.nodes:
        if node.type in {'BSDF_GLASS', 'BSDF_TRANSPARENT', 'BSDF_REFRACTION', 'BSDF_TRANSLUCENT', 'GROUP'}:
            return True
        if node.type == 'BSDF_PRINCIPLED':
            for key, is_alpha in [('Alpha', True), ('Transmission Weight', False), ('Transmission', False)]:
                sock = node.inputs.get(key)
                if sock and (sock.is_linked or (sock.default_value < 0.999 if is_alpha else sock.default_value > 0)):
                    return True
    return False


def review_reason(obj):
    reasons = []
    if any(transparent_material(slot.material) for slot in obj.material_slots):
        reasons.append('transparent material: not used as an occluder')
    if obj.animation_data or obj.constraints or (obj.data and obj.data.animation_data):
        reasons.append('animation, driver or constraint')
    if obj.library or obj.is_instancer or obj.type != 'MESH':
        reasons.append('linked data, instancer or non-mesh geometry')
    for mod in obj.modifiers:
        if mod.type in {'NODES', 'PARTICLE_SYSTEM', 'FLUID', 'OCEAN', 'CLOTH', 'SOFT_BODY', 'ARMATURE'}:
            reasons.append('procedural, simulated or deforming geometry')
    return '; '.join(reasons)


def protected_dependencies(scene):
    protected = set()
    for obj in scene.objects:
        if obj.parent:
            protected.add(obj.parent.name)
        for item in list(obj.modifiers) + list(obj.constraints):
            for prop in item.bl_rna.properties:
                if prop.type != 'POINTER' or prop.identifier == 'rna_type':
                    continue
                value = getattr(item, prop.identifier, None)
                if isinstance(value, bpy.types.Object):
                    protected.add(value.name)
                elif isinstance(value, bpy.types.Collection):
                    protected.update(o.name for o in value.all_objects)
    return protected


def collect_geometry(context, scope='SCENE'):
    if context.mode != 'OBJECT':
        raise RuntimeError('Please switch to Object Mode before scanning.')
    scene, layer = context.scene, context.view_layer
    available = [o for o in layer.objects if o.type in GEOMETRY_TYPES
                 and o.visible_get(view_layer=layer) and not o.hide_render]
    # Only selected objects AND their descendants define an assembly.
    selected = set(context.selected_objects)
    targets = set(available)
    if scope == 'SELECTED':
        targets = set()
        for obj in available:
            parent = obj
            while parent:
                if parent in selected:
                    targets.add(obj)
                    break
                parent = parent.parent
        available = [o for o in available if o in targets]
    if not targets:
        raise RuntimeError('No visible render-enabled geometry in the scan scope.')
    # Hidden/excluded/render-disabled objects are neither scanned nor unhidden.
    depsgraph = context.evaluated_depsgraph_get()
    depsgraph.update()
    deps = protected_dependencies(scene)
    records = []
    for obj in sorted(available, key=lambda o: o.name):
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        try:
            if not mesh:
                continue
            mesh.calc_loop_triangles()
            vertices = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
            mesh.vertices.foreach_get('co', vertices)
            vertices = vertices.reshape((-1, 3))
            mat = np.array(evaluated.matrix_world, dtype=np.float64)
            world = vertices.astype(np.float64) @ mat[:3, :3].T + mat[:3, 3]
            triangles = np.empty(len(mesh.loop_triangles) * 3, dtype=np.int32)
            mesh.loop_triangles.foreach_get('vertices', triangles)
            triangles = triangles.reshape((-1, 3))
            reason = review_reason(obj)
            if obj.name in deps:
                reason = '; '.join(filter(None, [reason, 'parent or geometry dependency']))
            if not len(triangles):
                reason = '; '.join(filter(None, [reason, 'no evaluated surface']))
            records.append({'name': obj.name, 'obj': obj, 'vertices': world,
                            'triangles': triangles, 'reason': reason,
                            'transparent': any(transparent_material(s.material) for s in obj.material_slots)})
        finally:
            evaluated.to_mesh_clear()
    if not records or not any(len(r['triangles']) for r in records):
        raise RuntimeError('No evaluated triangles found.')
    points = np.concatenate([r['vertices'] for r in records if len(r['vertices'])])
    minimum, maximum = points.min(axis=0), points.max(axis=0)
    center = (minimum + maximum) * 0.5
    scale = float(np.linalg.norm(maximum - minimum))
    if scale < 1e-15:
        raise RuntimeError('Geometry has a zero-size bounding box.')
    # Normalize CAD millimetres and very large world coordinates for both methods.
    for index, rec in enumerate(records):
        rec['id'] = index + 1
        rec['vertices'] = ((rec['vertices'] - center) / scale).astype(np.float32)
    return records


def sample_surface(rec, count):
    tri = rec['vertices'][rec['triangles']]
    if not len(tri):
        return []
    area = np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
    valid = np.flatnonzero(area > 1e-16)
    if not len(valid):
        return []
    # Half the budget samples faces uniformly; half is proportional to area.
    # This covers both small disconnected features and large CAD triangles.
    half = max(1, count // 2)
    by_index = valid[np.linspace(0, len(valid) - 1, min(half, len(valid)), dtype=int)]
    cumulative = np.cumsum(area[valid])
    by_area = valid[np.searchsorted(cumulative, (np.arange(half) + 0.5) * cumulative[-1] / half)]
    ids = np.unique(np.concatenate((by_index, by_area)))
    centers = tri[ids].mean(axis=1)
    # Add extrema so a tiny protruding tip isn't dependent only on face centers.
    verts = rec['vertices']
    extremes = np.unique(np.concatenate((verts.argmin(axis=0), verts.argmax(axis=0))))
    return [Vector(p) for p in np.concatenate((centers, verts[extremes]))]


class GPUPass:
    def __init__(self, records, resolution):
        import gpu
        from gpu_extras.batch import batch_for_shader
        self.gpu = gpu
        self.shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        self.batches = [(r['id'], batch_for_shader(self.shader, 'TRIS', {'pos': r['vertices']},
                        indices=r['triangles'])) for r in records
                        if not r['transparent'] and len(r['triangles'])]
        self.offscreen = gpu.types.GPUOffScreen(resolution, resolution, format='RGBA32F')
        self.resolution = resolution
        self.size = len(records) + 1

    def draw(self, direction, reverse=False):
        gpu = self.gpu
        direction = Vector(direction).normalized()
        rotation = (-direction).to_track_quat('-Z', 'Y')
        camera = rotation.to_matrix().to_4x4()
        camera.translation = direction * 2.0
        view = camera.inverted()
        # The normalized assembly fits inside radius 0.5, margin avoids clipping.
        radius, near, far = 0.53, 0.1, 4.0
        projection = Matrix(((1 / radius, 0, 0, 0), (0, 1 / radius, 0, 0),
                             (0, 0, -2 / (far - near), -(far + near) / (far - near)), (0, 0, 0, 1)))
        old_depth = gpu.state.depth_test_get()
        old_mask = gpu.state.depth_mask_get()
        old_blend = gpu.state.blend_get()
        old_viewport = gpu.state.viewport_get()
        try:
            with self.offscreen.bind():
                gpu.state.viewport_set(0, 0, self.resolution, self.resolution)
                gpu.state.depth_mask_set(True)
                gpu.state.depth_test_set('LESS_EQUAL')
                gpu.state.blend_set('NONE')
                gpu.state.face_culling_set('NONE')
                fb = gpu.state.active_framebuffer_get()
                fb.clear(color=(0, 0, 0, 0), depth=1.0)
                with gpu.matrix.push_pop(), gpu.matrix.push_pop_projection():
                    gpu.matrix.load_matrix(view)
                    gpu.matrix.load_projection_matrix(projection)
                    self.shader.bind()
                    batches = reversed(self.batches) if reverse else self.batches
                    for index, batch in batches:
                        # Float IDs, no lighting, materials, AA, tone mapping or RGB tolerance.
                        self.shader.uniform_float('color', (float(index), 0, 0, 1))
                        batch.draw(self.shader)
                pixels = np.asarray(fb.read_color(0, 0, self.resolution, self.resolution, 1, 0, 'FLOAT'))
                values = pixels.reshape(-1)
                rounded = np.rint(values).astype(np.int32)
                if np.any(np.abs(values - rounded) > 1e-4) or np.any(rounded < 0) or np.any(rounded >= self.size):
                    raise RuntimeError('GPU returned invalid object IDs; no classification was applied.')
                return np.bincount(rounded, minlength=self.size)
        finally:
            gpu.state.depth_test_set(old_depth)
            gpu.state.depth_mask_set(old_mask)
            gpu.state.blend_set(old_blend)
            gpu.state.face_culling_set('NONE')
            gpu.state.viewport_set(*old_viewport)

    def close(self):
        if self.offscreen:
            self.offscreen.free()
            self.offscreen = None


class BVHPass:
    def __init__(self, records):
        verts, tris, owners = [], [], []
        for rec in records:
            if rec['transparent'] or not len(rec['triangles']):
                continue
            offset = len(verts)
            verts.extend(rec['vertices'].tolist())
            tris.extend((rec['triangles'] + offset).tolist())
            owners.extend([rec['id']] * len(rec['triangles']))
        self.owners = owners
        self.tree = BVHTree.FromPolygons(verts, tris, all_triangles=True) if tris else None
        self.rays = 0

    def sees(self, point, direction, target):
        self.rays += 1
        if self.tree is None:
            return False
        # Cast FROM outside toward the surface. Never skip through a thin shell.
        hit, normal, index, distance = self.tree.ray_cast(point + direction * 2.0, -direction, 2.00001)
        return index is not None and self.owners[index] == target


class ScanJob:
    def __init__(self, context, method='HYBRID', scope='SCENE', views=100, resolution=512, samples=128):
        self.scene = context.scene
        self.scene_pointer = self.scene.as_pointer()
        self.frame = self.scene.frame_current
        self.method, self.views, self.resolution, self.samples = method, views, resolution, samples
        start = time.perf_counter()
        self.records = collect_geometry(context, scope)
        self.stats = {'preparation_seconds': time.perf_counter() - start,
                      'method': method, 'views': views, 'resolution': resolution, 'samples': samples,
                      'objects': len(self.records), 'triangles': sum(len(r['triangles']) for r in self.records)}
        self.hits = Counter()
        self.pixels = Counter()
        self.gpu_visible = set()
        self.bvh_visible = set()
        self.done = False
        self.progress = 'Preparing'
        self.gpu_pass = None
        self.iterator = self._run()

    def _gpu(self):
        start = time.perf_counter()
        try:
            self.gpu_pass = GPUPass(self.records, self.resolution)
            for number, direction in enumerate(directions(self.views)):
                counts = self.gpu_pass.draw(direction, reverse=bool(number % 2))
                for index in np.flatnonzero(counts[1:]) + 1:
                    self.gpu_visible.add(int(index))
                    self.hits[int(index)] += 1
                    self.pixels[int(index)] += int(counts[index])
                self.progress = 'GPU view %d / %d' % (number + 1, self.views)
                yield
        finally:
            if self.gpu_pass:
                self.gpu_pass.close()
                self.gpu_pass = None
        self.stats['gpu_seconds'] = time.perf_counter() - start

    def _bvh(self, targets):
        start = time.perf_counter()
        bvh = BVHPass(self.records)
        dirs = directions(self.views)
        pending = [r for r in self.records if r['id'] in targets and not r['transparent']]
        budget = 0
        for number, rec in enumerate(pending):
            self.progress = 'BVH object %d / %d' % (number + 1, len(pending))
            found = False
            # Process all directions for each sample; stop on one positive witness.
            for point in sample_surface(rec, self.samples):
                for direction in dirs:
                    if bvh.sees(point, direction, rec['id']):
                        self.bvh_visible.add(rec['id'])
                        found = True
                        break
                    budget += 1
                    if budget >= 1500:
                        budget = 0
                        yield
                if found:
                    break
            yield
        self.stats['bvh_seconds'] = time.perf_counter() - start
        self.stats['bvh_rays'] = bvh.rays

    def _run(self):
        all_ids = {r['id'] for r in self.records}
        if self.method in {'GPU', 'HYBRID', 'COMPARE'}:
            yield from self._gpu()
        if self.method in {'BVH', 'HYBRID', 'COMPARE'}:
            targets = all_ids - self.gpu_visible if self.method == 'HYBRID' else all_ids
            yield from self._bvh(targets)
        if self.method == 'GPU':
            visible = self.gpu_visible
        elif self.method == 'BVH':
            visible = self.bvh_visible
        else:
            visible = self.gpu_visible | self.bvh_visible
        self.categories = {'VISIBLE': [], 'CANDIDATE': [], 'REVIEW': []}
        for rec in self.records:
            category = 'VISIBLE' if rec['id'] in visible else 'REVIEW' if rec['reason'] else 'CANDIDATE'
            self.categories[category].append(rec['name'])
        self.stats.update({key.lower(): len(names) for key, names in self.categories.items()})
        self.stats['gpu_visible'] = len(self.gpu_visible)
        self.stats['bvh_visible'] = len(self.bvh_visible)
        if self.method == 'COMPARE':
            self.stats['gpu_only'] = [r['name'] for r in self.records if r['id'] in self.gpu_visible - self.bvh_visible]
            self.stats['bvh_only'] = [r['name'] for r in self.records if r['id'] in self.bvh_visible - self.gpu_visible]
        self.progress = 'Finished'

    def step(self, seconds=0.025):
        deadline = time.perf_counter() + seconds
        while time.perf_counter() < deadline:
            try:
                next(self.iterator)
            except StopIteration:
                self.done = True
                return True
        return False

    def close(self):
        self.iterator.close()
        if self.gpu_pass:
            self.gpu_pass.close()
            self.gpu_pass = None

    def apply(self):
        if not self.done:
            raise RuntimeError('Incomplete scans cannot be applied.')
        if self.scene.frame_current != self.frame:
            raise RuntimeError('Frame changed during scan; run again.')
        for rec in self.records:
            if self.scene.objects.get(rec['name']) != rec['obj']:
                raise RuntimeError('Objects changed during scan; run again.')
        # Build new results first. Never unlink objects from original collections.
        old_roots = [c for c in self.scene.collection.children if c.get('visibility_scanner_owner') == OWNER]
        root = bpy.data.collections.new('VIS_SCAN_RESULTS')
        root['visibility_scanner_owner'] = OWNER
        root['note'] = 'Additional links only. Candidates are not proof of enclosure. Current frame only.'
        self.scene.collection.children.link(root)
        children = []
        try:
            names = {'VISIBLE': 'VIS_可见_Visible', 'CANDIDATE': 'VIS_内部候选_Candidates', 'REVIEW': 'VIS_需复核_Review'}
            for category, label in names.items():
                child = bpy.data.collections.new(label)
                child['visibility_scanner_owner'] = OWNER
                child['category'] = category
                root.children.link(child)
                children.append(child)
                for name in self.categories[category]:
                    child.objects.link(self.scene.objects[name])
            for rec in self.records:
                category = next(k for k, names in self.categories.items() if rec['name'] in names)
                rec['obj']['vis_scan_category'] = category
                rec['obj']['vis_scan_note'] = rec['reason'] if rec['reason'] else 'Current frame, sampled external visibility only'
            for old in old_roots:
                # Only remove collections created by this tool; deleting a collection does not delete objects.
                for child in list(old.children):
                    if child.get('visibility_scanner_owner') == OWNER:
                        bpy.data.collections.remove(child)
                if not old.objects and not old.children:
                    bpy.data.collections.remove(old)
            root.name = 'VIS_SCAN_RESULTS'
            for child in children:
                child.name = names[child['category']]
        except Exception:
            for child in children:
                bpy.data.collections.remove(child)
            bpy.data.collections.remove(root)
            raise
        return self.stats


class VISSCAN_Settings(bpy.types.PropertyGroup):
    scope: EnumProperty(name='范围 / Scope', items=[('SCENE', '可见场景 / Visible scene', ''),
                        ('SELECTED', '所选装配体 / Selected assembly', 'Selected objects and descendants')])
    method: EnumProperty(name='方法 / Method', items=[
        ('HYBRID', 'GPU + BVH 复核（推荐）', 'GPU scan followed by surface rays for unseen objects'),
        ('GPU', 'GPU ID', 'Fast rasterized object visibility'),
        ('BVH', 'BVH 射线', 'Surface samples and exterior ray casting'),
        ('COMPARE', '比较两种方法 / Compare', 'Run both independently and keep union of visible objects')], default='HYBRID')
    views: IntProperty(name='方向数 / Views', default=100, min=12, max=1024)
    resolution: EnumProperty(name='GPU 分辨率', items=[(str(i), str(i), '') for i in (256, 512, 1024, 2048)], default='512')
    samples: IntProperty(name='每对象表面采样 / Samples', default=128, min=16, max=4096)
    running: BoolProperty(default=False, options={'SKIP_SAVE'})
    status: StringProperty(default='Ready / 就绪', options={'SKIP_SAVE'})


class VISSCAN_OT_scan(bpy.types.Operator):
    bl_idname = 'object.visibility_scan'
    bl_label = '🍊 检测并分类 / Scan and Classify'
    bl_options = {'REGISTER', 'UNDO'}
    _job = None
    _timer = None

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and not context.scene.vis_scan.running

    def execute(self, context):
        settings = context.scene.vis_scan
        try:
            self._job = ScanJob(context, settings.method, settings.scope, settings.views,
                                int(settings.resolution), settings.samples)
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        settings.running = True
        self._timer = context.window_manager.event_timer_add(0.025, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def finish(self, context):
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        if self._job:
            self._job.close()
        context.scene.vis_scan.running = False
        if context.area:
            context.area.tag_redraw()

    def modal(self, context, event):
        if event.type == 'ESC':
            context.scene.vis_scan.status = 'Cancelled / 已取消，未应用分类'
            self.finish(context)
            return {'CANCELLED'}
        if event.type != 'TIMER':
            # Block editing/navigation until snapshot classification is complete.
            return {'RUNNING_MODAL'}
        try:
            if self._job.step():
                stats = self._job.apply()
                elapsed = sum(stats.get(k, 0) for k in ('preparation_seconds', 'gpu_seconds', 'bvh_seconds'))
                context.scene.vis_scan.status = '可见 %d | 候选 %d | 复核 %d | %.2fs' % (
                    stats['visible'], stats['candidate'], stats['review'], elapsed)
                print('Visibility Scanner:', stats)
                self.report({'INFO'}, context.scene.vis_scan.status)
                self.finish(context)
                return {'FINISHED'}
            context.scene.vis_scan.status = self._job.progress
            if context.area:
                context.area.tag_redraw()
        except Exception as exc:
            context.scene.vis_scan.status = 'Failed / 失败: ' + str(exc)
            self.report({'ERROR'}, str(exc))
            self.finish(context)
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}


class VISSCAN_OT_select(bpy.types.Operator):
    bl_idname = 'object.visibility_scan_select'
    bl_label = '选择结果 / Select Result'
    bl_options = {'UNDO'}
    category: StringProperty()

    def execute(self, context):
        for obj in context.view_layer.objects:
            obj.select_set(False)
        chosen = []
        for root in context.scene.collection.children:
            if root.get('visibility_scanner_owner') != OWNER:
                continue
            for col in root.children:
                if col.get('category') == self.category:
                    for obj in col.objects:
                        if obj.name in context.view_layer.objects and obj.visible_get():
                            obj.select_set(True)
                            chosen.append(obj)
        if chosen:
            context.view_layer.objects.active = chosen[0]
        return {'FINISHED'}


class VISSCAN_PT_panel(bpy.types.Panel):
    bl_label = '🍊 可见性检测 / Visibility Scanner'
    bl_idname = 'VISSCAN_PT_panel'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = '🍊 橘子'

    def draw(self, context):
        layout, settings = self.layout, context.scene.vis_scan
        col = layout.column()
        col.enabled = not settings.running
        for field in ('scope', 'method', 'views', 'resolution', 'samples'):
            col.prop(settings, field)
        col.operator('object.visibility_scan', icon='VIEWZOOM')
        layout.label(text=settings.status)
        layout.label(text='仅分类，不删除；ESC 取消')
        layout.label(text='原集合保留；结果集合是额外链接')
        layout.label(text='候选仅代表本帧采样未发现可见部分')
        col = layout.column()
        col.enabled = not settings.running
        for category, label in [('VISIBLE', '选择可见'), ('CANDIDATE', '选择内部候选'), ('REVIEW', '选择需复核')]:
            op = col.operator('object.visibility_scan_select', text=label)
            op.category = category


CLASSES = (VISSCAN_Settings, VISSCAN_OT_scan, VISSCAN_OT_select, VISSCAN_PT_panel)


def registered_class(cls):
    if getattr(cls, 'is_registered', False):
        return cls
    if issubclass(cls, bpy.types.Operator):
        prefix, name = cls.bl_idname.split('.')
        return bpy.types.Operator.bl_rna_get_subclass_py(prefix.upper() + '_OT_' + name)
    base = bpy.types.Panel if issubclass(cls, bpy.types.Panel) else bpy.types.PropertyGroup
    return base.bl_rna_get_subclass_py(cls.__name__)


def register():
    values = {}
    if hasattr(bpy.types.Scene, 'vis_scan'):
        for scene in bpy.data.scenes:
            if scene.vis_scan.running:
                raise RuntimeError('Wait for the visibility scan to finish before reloading.')
            values[scene.name] = {key: getattr(scene.vis_scan, key) for key in
                                  ('scope', 'method', 'views', 'resolution', 'samples', 'status')}
    unregister()
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.vis_scan = PointerProperty(type=VISSCAN_Settings)
    for name, settings in values.items():
        for key, value in settings.items():
            setattr(bpy.data.scenes[name].vis_scan, key, value)


def unregister():
    if hasattr(bpy.types.Scene, 'vis_scan'):
        if any(scene.vis_scan.running for scene in bpy.data.scenes):
            raise RuntimeError('Wait for the visibility scan to finish before disabling.')
        del bpy.types.Scene.vis_scan
    for cls in reversed(CLASSES):
        previous = registered_class(cls)
        if previous:
            bpy.utils.unregister_class(previous)


if __name__ == '__main__':
    register()
