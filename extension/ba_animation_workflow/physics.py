"""Transactional MMD physics baking; the live scene is never used as a solver.

MMD Tools owns construction of its Bullet rig. BA owns isolation, sampling,
validation and reversible Action application. No MMD implementation is vendored.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import math
from statistics import median

import bpy
from mathutils import Matrix, Vector
from .utils import iter_action_fcurves

SCHEMA = 1
TRACK = 'mmd_tools_rigid_track'
SOURCE = 'baw_physics_source_action'
BACKUP = 'baw_physics_restore'
OUTPUT = 'baw_physics_output_action'


def mmd_api():
    for addon in bpy.context.preferences.addons:
        if addon.module.rsplit('.', 1)[-1] == 'mmd_tools':
            return importlib.import_module(addon.module + '.core.model'), addon.module
    raise ValueError('请先启用 MMD Tools；本功能使用它的刚体和关节构建规则')


def model_for(rig):
    if rig is None or rig.type != 'ARMATURE':
        raise ValueError('请选择当前场景中的 MMD 角色骨架')
    root = rig.parent
    while root and getattr(root, 'mmd_type', '') != 'ROOT':
        root = root.parent
    if not root:
        raise ValueError('该骨架不属于 MMD 模型')
    api, module = mmd_api()
    model = api.Model(root)
    if model.armature() != rig:
        raise ValueError('角色与 MMD 根对象的骨架绑定不一致')
    return model, module


def rna_values(value):
    """Deterministic shallow RNA values for scene-change guards and diagnostics."""
    if value is None:
        return None
    result = {}
    for p in value.bl_rna.properties:
        if p.identifier == 'rna_type' or p.type == 'COLLECTION':
            continue
        if p.is_readonly and p.identifier not in {'type'}:
            continue
        v = getattr(value, p.identifier)
        if p.type == 'POINTER':
            v = (v.name_full if isinstance(v, bpy.types.ID) else None)
        elif getattr(p, 'is_array', False):
            v = list(v)
        elif isinstance(v, set):
            v = sorted(v)
        result[p.identifier] = v
    return result


def action_signature(action):
    return [(fc.data_path, fc.array_index, fc.extrapolation, fc.mute,
             [rna_values(m) for m in fc.modifiers],
             [(list(k.co), list(k.handle_left), list(k.handle_right), k.interpolation,
               k.handle_left_type, k.handle_right_type) for k in fc.keyframe_points],
             [list(k.co) for k in fc.sampled_points]) for fc in iter_action_fcurves(action)]


def fingerprint(scene, rig):
    """Conservative: reject even unkeyed edits while an isolated job is running."""
    objects = []
    active_actions = set()
    drivers = []
    geometry = []
    custom_values = []
    def include_animation(owner):
        ad = owner.animation_data if owner else None
        if not ad:
            return
        if ad.action:
            active_actions.add(ad.action)
        if ad.use_nla:
            for track in ad.nla_tracks:
                if not track.mute:
                    for strip in track.strips:
                        if not strip.mute and strip.action:
                            active_actions.add(strip.action)
        for fc in ad.drivers:
            drivers.append([owner.name, fc.data_path, fc.array_index, fc.mute, rna_values(fc.driver),
                            [[rna_values(v), [rna_values(t) for t in v.targets]] for v in fc.driver.variables]])
    include_animation(scene)
    def custom(owner):
        def value(v):
            if isinstance(v, bpy.types.ID):
                return ('ID', v.name_full)
            if isinstance(v, dict):
                return {k: value(x) for k, x in v.items()}
            if isinstance(v, (list, tuple)):
                return [value(x) for x in v]
            if hasattr(v, 'to_dict'):
                return {k: value(x) for k, x in v.to_dict().items()}
            if hasattr(v, 'to_list'):
                return [value(x) for x in v.to_list()]
            return v
        result = {k: value(owner[k]) for k in owner.keys() if k != '_RNA_UI'}
        # The modal operator updates progress text; it is not a solver input.
        settings = result.get('baw_physics')
        if isinstance(settings, dict):
            settings.pop('status', None)
            if not settings:
                result.pop('baw_physics', None)
        return result
    custom_values.append([scene.name, custom(scene)])
    for o in sorted(scene.objects, key=lambda o: o.name):
        custom_values.append([o.name, custom(o)])
        include_animation(o)
        include_animation(o.data)
        if o.type == 'MESH':
            include_animation(o.data.shape_keys)
            if o.rigid_body:
                geometry.append([o.name, [list(v.co) for v in o.data.vertices], [list(f.vertices) for f in o.data.polygons]])
        ad = o.animation_data
        objects.append([o.name, list(o.location), list(o.rotation_euler),
                        list(o.rotation_quaternion), list(o.scale), o.rotation_mode,
                        o.parent.name if o.parent else None, o.parent_type, o.parent_bone,
                        [list(r) for r in o.matrix_parent_inverse],
                        [rna_values(c) for c in o.constraints],
                        rna_values(ad),
                        [[rna_values(t), [rna_values(st) for st in t.strips]] for t in ad.nla_tracks] if ad else [],
                        rna_values(o.rigid_body), rna_values(o.rigid_body_constraint),
                        rna_values(getattr(o, 'mmd_rigid', None)) if o.rigid_body else None])
    payload = [scene.name, scene.frame_current, scene.frame_subframe,
               scene.render.fps, scene.render.fps_base, scene.frame_start, scene.frame_end,
               scene.use_preview_range, scene.frame_preview_start, scene.frame_preview_end,
               list(scene.gravity), scene.use_gravity, rna_values(scene.rigidbody_world), objects,
               [(a.name, action_signature(a)) for a in sorted(active_actions, key=lambda a: a.name)], drivers, geometry, custom_values,
               [(b.name, rna_values(b), [rna_values(c) for c in b.constraints],
                 [list(row) for row in b.bone.matrix_local], b.parent.name if b.parent else None,
                 b.bone.inherit_scale, b.bone.use_inherit_rotation, b.bone.use_local_location)
                for b in rig.pose.bones]]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=list).encode()).hexdigest()


def infer_range(scene, rig):
    starts = [scene.frame_start]
    if scene.use_preview_range:
        starts.append(scene.frame_preview_start)
    if scene.rigidbody_world:
        starts.append(scene.rigidbody_world.point_cache.frame_start)
    ad = rig.animation_data
    if ad and ad.action:
        starts.append(math.floor(ad.action.frame_range[0]))
    return min(starts), scene.frame_end


def preflight(scene, rig, start, end):
    model, module = model_for(rig)
    if rig.name not in scene.objects or rig.library or rig.data.library:
        raise ValueError('需要当前场景中可编辑的本地骨架')
    if BACKUP in rig:
        raise ValueError('角色已有 BA 物理结果；请先恢复原状态再重新烘焙')
    if not isinstance(start, int) or not isinstance(end, int) or end <= start or end-start > 10000:
        raise ValueError('烘焙范围需要 2–10001 帧')
    ad = rig.animation_data
    if not ad or not ad.action:
        raise ValueError('角色需要一个有效的当前 Action')
    required_start, required_end = infer_range(scene, rig)
    required_end = max(required_end, math.ceil(ad.action.frame_range[1]))
    if start > required_start or end < required_end:
        raise ValueError(f'范围须覆盖完整动作、出片与预热：至少 {required_start}–{required_end} 帧')
    if ad.action_blend_type != 'REPLACE' or abs(ad.action_influence-1) > 1e-6:
        raise ValueError('请先将角色当前 Action 设为完全替换，避免叠加两次动作')
    if ad.use_nla and any(not t.mute for t in ad.nla_tracks):
        raise ValueError('角色含活动 NLA 层；请先合成为独立 Action 再烘焙物理')
    if len(ad.action.slots) != 1 or len(ad.action.layers) != 1:
        raise ValueError('当前支持单插槽、单层角色 Action；请先将复杂 Action 合成为独立动作')
    if len(ad.action.layers[0].strips) != 1:
        raise ValueError('当前支持单动作段的 Action')
    if rig.data.animation_data:
        raise ValueError('骨架数据自身含动画；请先固定骨架结构')
    if not all(math.isfinite(v) for v in (*scene.gravity, scene.render.fps_base)) or scene.render.fps_base <= 0:
        raise ValueError('场景重力或帧率无效')
    world = scene.rigidbody_world
    if world and world.point_cache.is_baking:
        raise ValueError('已有物理烘焙正在运行')
    if world and (world.point_cache.use_disk_cache or world.point_cache.use_external):
        raise ValueError('当前支持内存缓存；请在工程副本中将磁盘或外部缓存改为内存缓存后再运行')
    bodies = list(model.rigidBodies())
    joints = list(model.joints())
    names = sorted({o.mmd_rigid.bone for o in bodies if o.mmd_rigid.type in {'1', '2'} and o.mmd_rigid.bone})
    if not names:
        raise ValueError('没有绑定到骨骼的动态 MMD 刚体')
    for n in names:
        if n not in rig.pose.bones:
            raise ValueError('刚体绑定到不存在的骨骼：' + n)
        for c in rig.pose.bones[n].constraints:
            if c.name != TRACK and not c.mute and c.influence > 0:
                raise ValueError('物理骨骼还有其他有效约束，请先处理：' + n + ' / ' + c.name)
        if ad.drivers and any(fc.data_path.startswith(rig.pose.bones[n].path_from_id()) for fc in ad.drivers):
            raise ValueError('物理骨骼含驱动器，不能安全覆盖：' + n)
    owned = set(bodies)
    for o in scene.objects:
        if o.rigid_body and o not in owned and o.rigid_body.type == 'ACTIVE' and not o.rigid_body.kinematic:
            raise ValueError('存在其他动态刚体；请先隔离相互作用的物理系统：' + o.name)
    for o in bodies + joints:
        if o.library or not (o.rigid_body or o.rigid_body_constraint):
            raise ValueError('MMD 物理对象缺失或不可编辑：' + o.name)
        if o.animation_data and (o.animation_data.action or o.animation_data.drivers or o.animation_data.nla_tracks):
            raise ValueError('MMD 刚体或关节带有额外动画：' + o.name)
        if o.rigid_body_constraint:
            c = o.rigid_body_constraint
            if c.object1 not in owned or c.object2 not in owned:
                raise ValueError('关节端点缺失或跨模型：' + o.name)
    # The worker resamples motion, not time-varying solver properties or
    # collision geometry. Reject these instead of silently retiming them.
    for owner in [scene] + list(scene.objects):
        data = owner.animation_data
        if not data:
            continue
        curves = list(iter_action_fcurves(data.action)) + list(data.drivers)
        if any(fc.data_path.startswith(('rigid_body.', 'rigid_body_constraint.', 'rigidbody_world.', 'gravity', 'use_gravity')) for fc in curves):
            raise ValueError('物理求解参数带有动画，当前不能安全重采样：' + owner.name)
    for o in scene.objects:
        if o.rigid_body and (any(m.show_viewport for m in o.modifiers) or (o.type == 'MESH' and o.data.shape_keys)):
            raise ValueError('碰撞体含变形修改器或形态键，请先固定碰撞形状：' + o.name)
    return {'schema': SCHEMA, 'rig': rig.name, 'root': model.rootObject().name,
            'mmd_module': module, 'frames': [start, end], 'bones': names,
            'rigid_bodies': len(bodies), 'joints': len(joints),
            'fps': [scene.render.fps, scene.render.fps_base],
            'positive_offset': 1-start, 'source_action': ad.action.name,
            'note': '在独立副本中从正帧连续求解，结果映回原帧；负帧和第 0 帧都写入骨骼关键帧。'}


def rest_alignment(model, rig):
    """Only call after MMD clean, in the disposable worker.

    Child joint anchors often coincide with bone heads. A large, common offset
    across >= 4 anchors is evidence; normal COM offsets are never corrected.
    """
    diffs = []
    seen = set()
    inv = rig.matrix_world.inverted()
    for joint in model.joints():
        c = joint.rigid_body_constraint
        if not c or not c.object2:
            continue
        body = c.object2
        n = body.mmd_rigid.bone
        if n in seen or n not in rig.data.bones or body.mmd_rigid.type == '0':
            continue
        seen.add(n)
        # clean restores the rest-space joint coordinates, irrespective of current pose.
        diffs.append(rig.data.bones[n].head_local - inv @ joint.matrix_world.translation)
    height = max((b.head_local.z for b in rig.data.bones), default=1) - min((b.head_local.z for b in rig.data.bones), default=0)
    tolerance = max(height * .003, 1e-5)
    if not diffs:
        return {'offset': [0., 0., 0.], 'reliable': False, 'suspect': False, 'anchors': 0}
    offset = Vector([median([v[i] for v in diffs]) for i in range(3)])
    inliers = sum((v-offset).length <= tolerance for v in diffs)
    suspect = offset.length > max(height*.15, tolerance*10)
    reliable = suspect and len(diffs) >= 4 and inliers/len(diffs) >= .85
    return {'offset': list(offset), 'reliable': reliable, 'suspect': suspect,
            'anchors': len(diffs), 'inliers': inliers, 'tolerance': tolerance}


def pose_basis(bone, matrix, parent_matrix=None):
    args = {'invert': True}
    if bone.parent:
        args.update(parent_matrix=parent_matrix, parent_matrix_local=bone.parent.matrix_local)
    return bone.convert_local_to_pose(matrix, bone.matrix_local, **args)


def action_bag(action, slot):
    from bpy_extras.anim_utils import action_get_channelbag_for_slot
    return action_get_channelbag_for_slot(action, slot)


def write_samples(rig, action, slot, rows, names, start):
    """Bulk keys; deterministic quaternion signs; remove only owned channels."""
    bag = action_bag(action, slot)
    paths = {rig.pose.bones[n].path_from_id(p) for n in names
             for p in ('location', 'rotation_euler', 'rotation_quaternion', 'rotation_axis_angle', 'scale')}
    for fc in list(bag.fcurves):
        if fc.data_path in paths:
            bag.fcurves.remove(fc)
    for n in names:
        values = []
        previous = None
        for row in rows:
            loc, rot, scale = Matrix(row[n]).decompose()
            if not all(math.isfinite(x) for v in (loc, rot, scale) for x in v):
                raise ValueError('模拟产生非有限变换：' + n)
            if previous and rot.dot(previous) < 0:
                rot.negate()
            previous = rot.copy()
            values.append((loc, rot, scale))
        for col, path in enumerate(('location', 'rotation_quaternion', 'scale')):
            for index in range(len(values[0][col])):
                fc = bag.fcurves.new(rig.pose.bones[n].path_from_id(path), index=index)
                fc.keyframe_points.add(len(rows))
                fc.keyframe_points.foreach_set('co', [v for i, value in enumerate(values) for v in (start+i, value[col][index])])
                for key in fc.keyframe_points:
                    key.interpolation = 'LINEAR'
                fc.update()


def validate_result(result, report):
    if result.get('schema') != SCHEMA or result.get('frames') != report['frames'] or result.get('bones') != report['bones']:
        raise ValueError('物理结果版本、范围或骨骼与请求不一致')
    if result.get('status') != 'OK' or not result.get('verified'):
        raise ValueError('物理结果尚未通过验证')
    if result.get('rig') != report['rig'] or result.get('root') != report['root'] or result.get('fps') != report['fps']:
        raise ValueError('物理结果的角色或帧率不匹配')
    rows = result.get('basis', [])
    if len(rows) != report['frames'][1]-report['frames'][0]+1:
        raise ValueError('物理结果缺帧')
    for row in rows:
        if set(row) != set(report['bones']):
            raise ValueError('物理结果缺少骨骼')
        for m in row.values():
            if len(m) != 4 or any(len(r) != 4 or any(not isinstance(x, (int, float)) or not math.isfinite(x) for x in r) for r in m):
                raise ValueError('物理结果包含无效矩阵')
            if abs(Matrix(m).determinant()) < 1e-8:
                raise ValueError('物理结果包含不可逆矩阵')


def apply_result(scene, rig, result, report, expected_fingerprint=None):
    current_report = preflight(scene, rig, *report['frames'])
    validate_result(result, current_report)
    validate_result(result, report)
    if expected_fingerprint and fingerprint(scene, rig) != expected_fingerprint:
        raise ValueError('烘焙期间工程已改变，结果未应用；请按最新工程重新烘焙')
    ad = rig.animation_data
    source, source_slot = ad.action, ad.action_slot
    backup = {'slot': source_slot.identifier, 'world_enabled': scene.rigidbody_world.enabled if scene.rigidbody_world else None,
              'bones': {n: {'mode': rig.pose.bones[n].rotation_mode,
                           'mute': rig.pose.bones[n].constraints[TRACK].mute if TRACK in rig.pose.bones[n].constraints else None}
                        for n in report['bones']}}
    action = source.copy()
    try:
        action.name = source.name + '_BA物理'
        slot = action.slots[0]
        write_samples(rig, action, slot, result['basis'], report['bones'], report['frames'][0])
        action['baw_physics_result'] = True
        action['baw_physics_frames'] = report['frames']
        action['baw_physics_alignment'] = json.dumps(result.get('alignment', {}))
        rig[SOURCE] = source
        rig[OUTPUT] = action
        rig[BACKUP] = json.dumps(backup)
        ad.action = action
        ad.action_slot = slot
        for n in report['bones']:
            rig.pose.bones[n].rotation_mode = 'QUATERNION'
            c = rig.pose.bones[n].constraints.get(TRACK)
            if c:
                c.mute = True
        if scene.rigidbody_world:
            scene.rigidbody_world.enabled = False
        scene.frame_set(scene.frame_current, subframe=scene.frame_subframe)
        return action
    except Exception:
        ad.action = source
        ad.action_slot = source_slot
        _restore_flags(scene, rig, backup)
        for key in (SOURCE, OUTPUT, BACKUP):
            if key in rig:
                del rig[key]
        bpy.data.actions.remove(action)
        raise


def _restore_flags(scene, rig, backup):
    for n, value in backup['bones'].items():
        b = rig.pose.bones.get(n)
        if b:
            b.rotation_mode = value['mode']
            c = b.constraints.get(TRACK)
            if c and value['mute'] is not None:
                c.mute = value['mute']
    if scene.rigidbody_world and backup['world_enabled'] is not None:
        scene.rigidbody_world.enabled = backup['world_enabled']


def restore(scene, rig):
    if rig is None or BACKUP not in rig or SOURCE not in rig:
        raise ValueError('该角色没有可恢复的 BA 物理结果')
    source = rig[SOURCE]
    if not isinstance(source, bpy.types.Action):
        raise ValueError('原始 Action 已丢失，未修改当前结果')
    ad = rig.animation_data
    if not ad or not ad.action or ad.action != rig.get(OUTPUT):
        raise ValueError('当前 Action 已被替换；请切回 BA 物理结果后恢复')
    backup = json.loads(rig[BACKUP])
    slot = next((s for s in source.slots if s.identifier == backup['slot']), None)
    if slot is None:
        raise ValueError('原始 Action 插槽已丢失')
    for n, value in backup['bones'].items():
        if n not in rig.pose.bones or (value['mute'] is not None and TRACK not in rig.pose.bones[n].constraints):
            raise ValueError('烘焙后骨架或物理绑定已改变，请先恢复绑定：' + n)
    # Keep the result as an editable alternate, including any subsequent user edits.
    ad.action.use_fake_user = True
    ad.action = source
    ad.action_slot = slot
    _restore_flags(scene, rig, backup)
    del rig[SOURCE]
    del rig[OUTPUT]
    del rig[BACKUP]
    scene.frame_set(scene.frame_current, subframe=scene.frame_subframe)
