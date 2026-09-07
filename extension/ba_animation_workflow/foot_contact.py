"""Opt-in, reuse-only foot contact bake. No persistent IK constraints."""
from __future__ import annotations

import importlib
import json
import math

import bpy
from mathutils import Matrix, Vector


def _mapping(source, target):
    bridge = bpy.context.scene.ba_motion_bridge_settings
    package = type(bridge).__module__.rsplit('.', 1)[0]
    return importlib.import_module(package + '.mapping').build_mapping(source, target)


def _smooth(value):
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def contact_ranges(points, leg_length, fps, floor=None):
    """Conservative low-height, low-speed support runs; lifted feet stay free."""
    if len(points) < 4 or leg_length <= 1e-8:
        return []
    floor = min(p.z for p in points) if floor is None else floor
    speed_limit = leg_length * 0.08 / max(1.0, fps)
    flags = []
    for i, point in enumerate(points):
        speed = max((point - points[max(0, i-1)]).length,
                    (points[min(len(points)-1, i+1)] - point).length)
        flags.append(point.z <= floor + leg_length * 0.025 and speed <= speed_limit)
    runs, start = [], None
    for i, flag in enumerate([*flags, False]):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            if (i - start >= max(4, round(fps * 0.15))
                    and max((p-points[start]).length for p in points[start:i]) <= leg_length * .025):
                runs.append((start, i-1))
            start = None
    return runs


def capture_root(scene, source, target, action, start, end):
    """Read the raw root placement before BA continuity rebases it."""
    mapping = _mapping(source, target)
    pairs = {p.role: p for p in mapping.pairs}
    if mapping.target_profile != 'MMD' or not all(k in pairs for k in ('hips_rotation','root_xy')):
        raise RuntimeError('实验防脚滑当前仅支持可识别腿链的 MMD 模型')
    hips, center = pairs['hips_rotation'].target, pairs['root_xy'].target
    ad = target.animation_data
    old_frame, old_nla = scene.frame_current, ad.use_nla
    old_action = ad.action
    samples = {}
    try:
        ad.action = action
        ad.use_nla = False
        for f in range(start, end+1):
            scene.frame_set(f); bpy.context.view_layer.update()
            samples[f] = ((target.matrix_world @ target.pose.bones[center].matrix).translation.copy(),
                          (target.matrix_world @ target.pose.bones[hips].matrix).to_quaternion())
    finally:
        ad.action, ad.use_nla = old_action, old_nla
        scene.frame_set(old_frame)
    return mapping, center, hips, samples


def _aim(bone, goal):
    axis = bone.tail - bone.head
    wanted = goal - bone.head
    if min(axis.length, wanted.length) < 1e-8:
        return
    loc, rot, scale = bone.matrix.decompose()
    bone.matrix = Matrix.LocRotScale(loc, axis.rotation_difference(wanted) @ rot, scale)
    bpy.context.view_layer.update()


def _solve(target, names, goal_world):
    upper, lower, foot = (target.pose.bones[n] for n in names)
    hip, knee, ankle = (b.head.copy() for b in (upper, lower, foot))
    goal = target.matrix_world.inverted_safe() @ goal_world
    a, b = (knee-hip).length, (ankle-knee).length
    direction = goal-hip
    distance = direction.length
    if min(a,b,distance) < 1e-8:
        return False, 0.0
    if (goal-ankle).length < 1e-7:
        return True, (target.matrix_world @ foot.head-goal_world).length
    direction.normalize()
    # The raw bend plane belongs to the original hip-to-ankle axis, NOT
    # the new goal axis. Projecting the old knee onto the new axis creates
    # a different plane and forces knee sideways rotation (up to 29 degrees
    # on the real ninth clip). Transport the entire plane as a rigid frame.
    original_axis = ankle-hip
    if original_axis.length < 1e-8:
        return False, distance
    original_axis.normalize()
    pole = knee-hip - original_axis*(knee-hip).dot(original_axis)
    if pole.length < (a+b)*1e-3:
        # MMD knees hinge about local X. Use that anatomical axis at the
        # straight-leg singularity, never an arbitrary world-space pole.
        hinge = lower.matrix.to_3x3() @ Vector((1,0,0))
        pole = original_axis.cross(hinge)
    if pole.length < 1e-6:
        return False, distance
    pole.normalize()
    transport = original_axis.rotation_difference(direction)
    pole = transport @ pole
    # Keep a tiny positive bend instead of solving exactly at singular reach.
    maximum = math.sqrt(a*a+b*b+2*a*b*math.cos(math.radians(1.0)))
    reach = min(max(distance, abs(a-b)+1e-6), maximum)
    along = (a*a-b*b+reach*reach)/(2*reach)
    desired_knee = hip + direction*along + pole*math.sqrt(max(0,a*a-along*along))
    rotation = foot.matrix.to_quaternion()
    loc, rot, scale = upper.matrix.decompose()
    upper.matrix = Matrix.LocRotScale(loc, transport @ rot, scale)
    bpy.context.view_layer.update()
    _aim(upper, desired_knee)
    _aim(lower, hip+direction*reach)
    loc, _, scale = foot.matrix.decompose()
    foot.matrix = Matrix.LocRotScale(loc, rotation, scale)
    bpy.context.view_layer.update()
    return True, (target.matrix_world @ foot.head-goal_world).length


def apply(scene, source, target, action, start, end, raw):
    """Bake contacts onto a fresh reuse output, after continuity, before linking."""
    mapping, center, hips, root_samples = raw
    pairs = {p.role:p for p in mapping.pairs}
    chains = []
    for side in ('left','right'):
        roles = [side+'_'+part for part in ('thigh','shin','foot')]
        if any(r not in pairs for r in roles):
            raise RuntimeError('实验防脚滑无法识别完整双腿；未替换原动作')
        names = tuple(pairs[r].target for r in roles)
        bones = [target.pose.bones[n] for n in names]
        if bones[1].parent != bones[0] or bones[2].parent != bones[1]:
            raise RuntimeError('实验防脚滑暂不支持带中间控制骨的腿链')
        if any(not c.mute and c.influence > 1e-6 for bone in bones for c in bone.constraints):
            raise RuntimeError('实验防脚滑检测到活动腿部约束，已停止以避免破坏绑定')
        source_names = tuple(pairs[r].source for r in roles)
        rest = [source.matrix_world @ source.data.bones[n].head_local for n in source_names]
        length = (rest[1]-rest[0]).length + (rest[2]-rest[1]).length
        chains.append((names, source_names[-1], length))
    ad = target.animation_data
    old_frame, old_nla, old_action = scene.frame_current, ad.use_nla, ad.action
    baseline = None
    try:
        ad.action, ad.use_nla = action, False
        # Store A before either root correction or contact solve. It is not a
        # reusable clip candidate, so Text replacement cannot consume it.
        baseline = action.copy()
        baseline.name = action.name + '_防脚滑对比_关闭'
        baseline['bam_role'] = 'FOOT_CONTACT_BASELINE'
        baseline.use_fake_user = True
        source_points = {names:[] for names,_,_ in chains}
        release = min(end, start+max(2, round(scene.render.fps / scene.render.fps_base * .25)))
        scene.frame_set(release); bpy.context.view_layer.update()
        delta = (target.matrix_world @ target.pose.bones[hips].matrix).to_quaternion() @ root_samples[release][1].inverted()
        # Keep only world yaw; the released continuity delta should be yaw,
        # but projection also protects against numerical/rest-pose differences.
        from mathutils import Quaternion
        yaw = Quaternion((delta.w,0,0,delta.z))
        if yaw.magnitude < 1e-8:
            yaw = Quaternion()
        yaw.normalize()
        original_feet = {}
        for f in range(start,end+1):
            scene.frame_set(f); bpy.context.view_layer.update()
            for names, source_foot, _ in chains:
                source_points[names].append((source.matrix_world @ source.pose.bones[source_foot].head).copy())
            offset = root_samples[f][0]-root_samples[start][0]
            bone = target.pose.bones[center]
            matrix = bone.matrix.copy()
            matrix.translation += target.matrix_world.to_3x3().inverted_safe() @ (yaw @ offset-offset)
            bone.matrix = matrix
            bone.keyframe_insert('location',frame=f)
            bpy.context.view_layer.update()
            original_feet[f] = {names:(target.matrix_world @ target.pose.bones[names[-1]].head).copy() for names,_,_ in chains}
        fps = scene.render.fps / scene.render.fps_base
        floor = min(p.z for points in source_points.values() for p in points)
        ranges = {names:contact_ranges(source_points[names],length,fps,floor) for names,_,length in chains}
        goals = {}
        ramp = max(2, round(fps * .15))
        for names, runs in ranges.items():
            for first,last in runs:
                anchor = original_feet[start+first][names]
                for i in range(first,last+1):
                    weight = _smooth((i-first)/ramp)
                    if last < end-start:
                        weight *= _smooth((last-i)/ramp)
                    goals.setdefault(start+i,{})[names] = original_feet[start+i][names].lerp(anchor,weight)
        # Cache all raw local rotations before key insertion; newly inserted
        # quaternion keys must not change the next frame's raw interpolation.
        matrices = {}
        for f in range(start,end+1):
            scene.frame_set(f); bpy.context.view_layer.update()
            matrices[f] = {n:target.pose.bones[n].matrix_basis.copy() for names,_,_ in chains for n in names}
        corrected, max_error = 0, 0.0
        previous_rotations = {}
        for f in range(start,end+1):
            scene.frame_set(f)
            for n,matrix in matrices[f].items():
                target.pose.bones[n].matrix_basis = matrix
            bpy.context.view_layer.update()
            for names, goal in goals.get(f,{}).items():
                success, error = _solve(target,names,goal)
                corrected += int(success)
                max_error = max(max_error,error)
            # Dense keys include swing frames: released feet retain raw motion.
            for n in matrices[f]:
                bone = target.pose.bones[n]
                path = 'rotation_quaternion' if bone.rotation_mode == 'QUATERNION' else ('rotation_axis_angle' if bone.rotation_mode == 'AXIS_ANGLE' else 'rotation_euler')
                if path == 'rotation_quaternion':
                    q = bone.rotation_quaternion.copy()
                    if n in previous_rotations and previous_rotations[n].dot(q) < 0:
                        q.negate(); bone.rotation_quaternion=q
                    previous_rotations[n]=q
                elif path == 'rotation_euler':
                    q=bone.rotation_euler.copy()
                    if n in previous_rotations:
                        q.make_compatible(previous_rotations[n]); bone.rotation_euler=q
                    previous_rotations[n]=q
                bone.keyframe_insert(path,frame=f,group=n)
        action['baw_foot_contact_enabled'] = True
        action['baw_foot_contact_baseline'] = baseline.name
        action['baw_foot_contact_report'] = json.dumps({'ranges':{names[-1]:[[start+x,start+y] for x,y in runs] for names,runs in ranges.items()},'solved_samples':corrected,'max_residual':max_error},ensure_ascii=False)
        return baseline
    except Exception:
        if baseline is not None:
            bpy.data.actions.remove(baseline)
        raise
    finally:
        ad.action, ad.use_nla = old_action, old_nla
        scene.frame_set(old_frame)
