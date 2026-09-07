"""Reuse-only, one-sided pose/velocity blend. Never edit the previous clip."""
from __future__ import annotations

import json
import math

import bpy
from mathutils import Quaternion


def _unit_shortest(q):
    q = q.normalized()
    if q.w < 0:
        q.negate()
    return q


def _prediction_time(frame, duration):
    # Preserve exactly one incoming step, then damp extrapolation so an arm
    # does not keep swinging indefinitely while the new clip fades in.
    if frame <= 1:
        return float(frame)
    tau = max(1.0, duration * .25)
    return 1.0 + tau * (1.0 - math.exp(-(frame-1)/tau))


def _weight(frame, duration):
    # Two untouched outgoing samples make the release finite difference
    # equal to the baseline; the first two samples match incoming velocity.
    t = max(0.0, min(1.0, (frame-1)/max(1,duration-2)))
    return t*t*t*(10+t*(-15+6*t))


def apply(scene, target, action, previous, start, end, frames):
    from .auto_director import _action_bone_channels, _clip_motion_bounds, _iter_action_fcurves

    action['baw_seam_smoothing_enabled'] = False
    if previous is None or _clip_motion_bounds(previous)[1] != start:
        action['baw_seam_smoothing_status'] = 'NO_ADJACENT_CLIP'
        return False
    duration = min(int(frames), end-start)
    if duration < 4:
        action['baw_seam_smoothing_status'] = 'CLIP_TOO_SHORT'
        return False
    channels = _action_bone_channels(action)
    previous_channels = _action_bone_channels(previous)
    names = [b.name for b in target.pose.bones if b.name in channels and b.name in previous_channels]
    if not names:
        action['baw_seam_smoothing_status'] = 'NO_COMMON_CHANNELS'
        return False
    ad = target.animation_data
    old_action, old_nla, old_frame = ad.action, ad.use_nla, scene.frame_current
    old_slot = getattr(ad,'action_slot',None)
    baseline = None
    try:
        ad.use_nla = False
        def sample(act, frame):
            ad.action = act
            scene.frame_set(frame); bpy.context.view_layer.update()
            rows = {}
            for n in names:
                bone = target.pose.bones[n]
                loc,rot,scale = bone.matrix_basis.decompose()
                if bone.rotation_mode == 'QUATERNION' and rot.dot(bone.rotation_quaternion)<0:
                    rot.negate()
                rows[n] = loc,rot,scale
            return rows
        before = sample(previous,start-1)
        boundary = sample(previous,start)
        raw = {i:sample(action,start+i) for i in range(duration+1)}
        baseline = action.copy()
        baseline.name = action.name + '_防突变对比_关闭'
        baseline['bam_role'] = 'SEAM_SMOOTHING_BASELINE'
        baseline.use_fake_user = True
        last_rotations = {}
        for i in range(duration-1):
            f = start+i
            scene.frame_set(f)
            t = _prediction_time(i,duration)
            weight = _weight(i,duration)
            for name in names:
                bone = target.pose.bones[name]
                paths = channels[name] & previous_channels[name]
                loc0,rot0,scale0 = before[name]
                loc1,rot1,scale1 = boundary[name]
                loc_raw,rot_raw,scale_raw = raw[i][name]
                if 'location' in paths:
                    bone.location = (loc1+(loc1-loc0)*t).lerp(loc_raw,weight)
                    bone.keyframe_insert('location',frame=f,group=name)
                rotation_paths = paths & {'rotation_quaternion','rotation_euler','rotation_axis_angle'}
                if rotation_paths:
                    velocity = _unit_shortest(rot0.inverted() @ rot1)
                    predicted = rot1 @ Quaternion(velocity.axis, velocity.angle*t)
                    value = predicted.slerp(rot_raw,weight).normalized()
                    if 'rotation_quaternion' in paths:
                        reference = last_rotations.get(name,rot_raw)
                        if reference.dot(value)<0:
                            value.negate()
                        bone.rotation_quaternion=value
                        last_rotations[name]=value.copy()
                        path='rotation_quaternion'
                    elif 'rotation_euler' in paths:
                        value=value.to_euler(bone.rotation_mode)
                        if name in last_rotations:
                            value.make_compatible(last_rotations[name])
                        bone.rotation_euler=value
                        last_rotations[name]=value.copy()
                        path='rotation_euler'
                    else:
                        value=_unit_shortest(value)
                        bone.rotation_axis_angle=(value.angle,*value.axis)
                        path='rotation_axis_angle'
                    bone.keyframe_insert(path,frame=f,group=name)
                if 'scale' in paths:
                    # Never extrapolate scale: preserve size at the seam.
                    bone.scale = scale1.lerp(scale_raw,weight)
                    bone.keyframe_insert('scale',frame=f,group=name)
            bpy.context.view_layer.update()
        # Only new, in-window segments are linear. Keep the release/end keys
        # and all their handles untouched; do not overshoot with auto Bezier.
        owned_paths = {target.pose.bones[n].path_from_id(p) for n in names
                       for p in channels[n] & previous_channels[n]}
        for curve in _iter_action_fcurves(action):
            if curve.data_path in owned_paths:
                for key in curve.keyframe_points:
                    if start <= key.co.x < start+duration-1:
                        key.interpolation = 'LINEAR'
        # Key insertion can recalculate AUTO handles on neighbouring keys.
        # Restore the untouched side from the A/B baseline as well as values.
        baseline_curves = {(c.data_path,c.array_index):c for c in _iter_action_fcurves(baseline)}
        for curve in _iter_action_fcurves(action):
            original = baseline_curves.get((curve.data_path,curve.array_index))
            if original is None:
                continue
            points = {float(k.co.x):k for k in original.keyframe_points}
            for key in curve.keyframe_points:
                if start <= key.co.x < start+duration-1:
                    continue
                prior = points.get(float(key.co.x))
                if prior is not None:
                    key.interpolation = prior.interpolation
                    key.handle_left_type = prior.handle_left_type
                    key.handle_right_type = prior.handle_right_type
                    key.handle_left = prior.handle_left
                    key.handle_right = prior.handle_right
        action['baw_seam_smoothing_enabled'] = True
        action['baw_seam_smoothing_status'] = 'APPLIED'
        action['baw_seam_smoothing_baseline'] = baseline.name
        action['baw_seam_smoothing_report'] = json.dumps({'start':start,'release':start+duration,
            'frames':duration,'previous':previous.name,'bones':len(names)},ensure_ascii=False)
        return True
    except Exception:
        if baseline is not None:
            bpy.data.actions.remove(baseline)
        raise
    finally:
        ad.action, ad.use_nla = old_action,old_nla
        if old_slot is not None and old_action is not None:
            ad.action_slot = old_slot
        scene.frame_set(old_frame)
