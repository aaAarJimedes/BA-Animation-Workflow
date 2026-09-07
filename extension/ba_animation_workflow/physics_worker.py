"""Run only in a disposable Blender process, using a snapshot and JSON job.

The source animation is evaluated at its real times before solving. Evaluated
poses and collider transforms are sampled to a positive-time working Action;
this preserves NLA/driver timing without rewriting arbitrary expressions.
Frame zero in Blender 5.1's point cache is reserved for cache metadata.
"""
from __future__ import annotations

import importlib
import json
import math
from pathlib import Path
import sys
import traceback

import bpy
from mathutils import Matrix


def matrix_rows(matrix):
    return [list(row) for row in matrix]


def atomic_json(path, payload):
    path = Path(path)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf8')
    tmp.replace(path)


def solve(job, core):
    def progress(stage, frame=0, total=1):
        atomic_json(job['progress'], {'stage': stage, 'done': frame, 'total': total})

    bpy.ops.wm.open_mainfile(filepath=job['snapshot'], load_ui=False, use_scripts=False)
    if job['mmd_module'] not in bpy.context.preferences.addons:
        import addon_utils
        addon_utils.enable(job['mmd_module'], default_set=False, persistent=False)
    scene = bpy.data.scenes[job['scene']]
    bpy.context.window.scene = scene
    rig = bpy.data.objects[job['rig']]
    start, end = job['frames']
    report = core.preflight(scene, rig, start, end)
    model, _ = core.model_for(rig)
    world = scene.rigidbody_world
    if world:
        # Never touch caches on disk, even in a snapshot that still refers to them.
        # preflight rejects external/disk caches. Do not even reassign the
        # unchanged disk flag: Blender 5.1 can crash in its RNA update callback.
        with bpy.context.temp_override(scene=scene, point_cache=world.point_cache):
            bpy.ops.ptcache.free_bake()
        world.enabled = False
    model.clean()
    scene.frame_set(start)
    bpy.context.view_layer.update()
    alignment = core.rest_alignment(model, rig)
    alignment['applied'] = False
    if alignment['suspect']:
        if not alignment['reliable']:
            raise ValueError('刚体与骨骼疑似错位，但偏移不一致；请先检查模型关节位置')
        if not job.get('align', True):
            raise ValueError('检测到统一的物理布局偏移；请开启“校正已确认的统一偏移”后重试')
        from mathutils import Vector
        delta = rig.matrix_world.to_3x3() @ Vector(alignment['offset'])
        for o in list(model.rigidBodies()) + list(model.joints()):
            m = o.matrix_world.copy()
            m.translation += delta
            o.matrix_world = m
        bpy.context.view_layer.update()
        alignment['applied'] = True
    progress('采样原时间轴动作')
    owned = set(model.rigidBodies())
    external = [o for o in scene.objects if o.rigid_body and o not in owned]
    names = [b.name for b in rig.pose.bones]
    source_rows, object_rows, external_rows = [], [], []
    total = end-start+1
    for i, frame in enumerate(range(start, end+1)):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        deps = bpy.context.evaluated_depsgraph_get()
        ev = rig.evaluated_get(deps)
        source_rows.append({n: matrix_rows(core.pose_basis(ev.pose.bones[n].bone, ev.pose.bones[n].matrix,
                            ev.pose.bones[n].parent.matrix if ev.pose.bones[n].parent else None)) for n in names})
        object_rows.append(matrix_rows(ev.matrix_world))
        external_rows.append({o.name: matrix_rows(o.evaluated_get(deps).matrix_world) for o in external})
        if i % 20 == 0:
            progress('采样原时间轴动作', i, total)

    scene.frame_set(start)
    bpy.context.view_layer.update()
    model.build()
    world = scene.rigidbody_world
    if not world:
        raise ValueError('MMD Tools 未创建物理世界')
    world.enabled = False
    world.substeps_per_frame = job.get('substeps', world.substeps_per_frame)
    world.solver_iterations = job.get('iterations', world.solver_iterations)
    for b in rig.pose.bones:
        for c in b.constraints:
            c.mute = c.name != core.TRACK
        b.rotation_mode = 'QUATERNION'
    for c in rig.constraints:
        c.mute = True
    rig.animation_data_clear()
    rig.parent = None
    rig.matrix_parent_inverse.identity()
    rig.rotation_mode = 'QUATERNION'
    # Seed Blender's layered Action, then fill its channelbag in bulk.
    rig.pose.bones[0].keyframe_insert('location', frame=1)
    action = rig.animation_data.action
    action.name = 'BA_PHYSICS_WORKING_POSE'
    core.write_samples(rig, action, rig.animation_data.action_slot, source_rows, names, 1)
    bag = core.action_bag(action, rig.animation_data.action_slot)

    def object_keys(obj, matrices, existing_bag=None):
        obj.animation_data_clear() if obj != rig else None
        obj.parent = None
        obj.matrix_parent_inverse.identity()
        for c in obj.constraints:
            c.mute = True
        obj.rotation_mode = 'QUATERNION'
        if existing_bag is None:
            obj.keyframe_insert('location', frame=1)
            existing_bag = core.action_bag(obj.animation_data.action, obj.animation_data.action_slot)
        for fc in list(existing_bag.fcurves):
            if fc.data_path in {'location', 'rotation_quaternion', 'scale'}:
                existing_bag.fcurves.remove(fc)
        values = []
        previous = None
        for m in matrices:
            loc, rot, scale = Matrix(m).decompose()
            if previous and rot.dot(previous) < 0:
                rot.negate()
            previous = rot.copy()
            values.append((loc, rot, scale))
        for col, path in enumerate(('location', 'rotation_quaternion', 'scale')):
            for index in range(len(values[0][col])):
                fc = existing_bag.fcurves.new(path, index=index)
                fc.keyframe_points.add(total)
                fc.keyframe_points.foreach_set('co', [v for i, value in enumerate(values) for v in (i+1, value[col][index])])
                for key in fc.keyframe_points:
                    key.interpolation = 'LINEAR'
                fc.update()
    object_keys(rig, object_rows, bag)
    for o in external:
        object_keys(o, [row[o.name] for row in external_rows])
    # Dynamic bodies and joints begin at the built world transform. Keep MMD
    # kinematic bodies bone-parented; they follow the sampled original rig.
    for o in list(model.rigidBodies()) + list(model.joints()):
        if o.rigid_body and o.mmd_rigid.type == '0':
            continue
        m = o.matrix_world.copy()
        o.parent = None
        o.matrix_parent_inverse.identity()
        o.matrix_world = m
        for c in o.constraints:
            c.mute = True
    scene.frame_start = 1
    scene.frame_end = total
    scene.use_preview_range = False
    cache = world.point_cache
    cache.frame_start = 1
    cache.frame_end = total
    with bpy.context.temp_override(scene=scene, point_cache=cache):
        bpy.ops.ptcache.free_bake()
    scene.frame_set(1)
    world.enabled = True
    bpy.context.view_layer.update()
    rows, expected, jumps = [], [], []
    previous = {}
    for i, frame in enumerate(range(1, total+1)):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        ev = rig.evaluated_get(bpy.context.evaluated_depsgraph_get())
        row, comparison = {}, {}
        for n in report['bones']:
            b = ev.pose.bones[n]
            row[n] = matrix_rows(core.pose_basis(b.bone, b.matrix, b.parent.matrix if b.parent else None))
            m = ev.matrix_world @ b.matrix
            comparison[n] = matrix_rows(m)
            q = m.to_quaternion().normalized()
            if n in previous:
                angle = math.degrees(2 * math.acos(min(1., abs(q.dot(previous[n])))))
                jumps.append({'bone': n, 'frame': start+i, 'degrees': angle})
            previous[n] = q.copy()
        rows.append(row)
        expected.append(comparison)
        if i % 20 == 0:
            progress('连续模拟头发与衣物', i, total)
    result = dict(report, status='OK', basis=rows, alignment=alignment, verified=True,
                  largest_steps=sorted(jumps, key=lambda x: x['degrees'], reverse=True)[:12],
                  zero_steps=[j for j in jumps if j['frame'] in {0, 1}],
                  solver={'substeps': world.substeps_per_frame, 'iterations': world.solver_iterations})
    core.validate_result(result, report)

    # Reopen pristine input and check the same application path the user gets.
    # This catches doubled constraints, local-space errors and unsupported rigs.
    progress('复核原工程中的骨骼结果')
    bpy.ops.wm.open_mainfile(filepath=job['snapshot'], load_ui=False, use_scripts=False)
    scene = bpy.data.scenes[job['scene']]
    bpy.context.window.scene = scene
    rig = bpy.data.objects[job['rig']]
    core.apply_result(scene, rig, result, report)
    max_error = 0.
    for i, frame in enumerate(range(start, end+1)):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        ev = rig.evaluated_get(bpy.context.evaluated_depsgraph_get())
        for n in report['bones']:
            actual = ev.matrix_world @ ev.pose.bones[n].matrix
            error = max(abs(actual[r][c]-expected[i][n][r][c]) for r in range(4) for c in range(4))
            max_error = max(max_error, error)
        if i % 20 == 0:
            progress('复核原工程中的骨骼结果', i, total)
    if max_error > 0.0002:
        raise ValueError(f'原骨架回放与物理结果不一致（误差 {max_error:.6g}），未应用')
    result['max_replay_matrix_error'] = max_error
    atomic_json(job['result'], result)
    progress('验证通过', total, total)


if __name__ == '__main__':
    job = json.loads(Path(sys.argv[sys.argv.index('--')+1]).read_text(encoding='utf8'))
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        core = importlib.import_module(Path(__file__).resolve().parent.name + '.physics')
        solve(job, core)
    except Exception as exc:
        atomic_json(job['result'], {'status': 'ERROR', 'error': str(exc), 'traceback': traceback.format_exc()})
        traceback.print_exc()
        sys.exit(1)
