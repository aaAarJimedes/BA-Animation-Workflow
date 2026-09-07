"""Transactional, two-sided seam blend with reversible previous-tail edits."""
from __future__ import annotations

import hashlib
import json
import math

import bpy
from mathutils import Quaternion, Vector


def _step(q, factor):
    # atan2 avoids acos(w)'s loss of precision for tiny seam velocities.
    vector = Vector((q.x,q.y,q.z))
    length = vector.length
    return Quaternion() if length<1e-12 else Quaternion(vector/length,2*math.atan2(length,q.w)*factor)


def _curves(action):
    from .auto_director import _iter_action_fcurves
    return {(c.data_path,c.array_index):c for c in _iter_action_fcurves(action)}


def snapshot(action):
    return {key:[dict(co=list(p.co), left=list(p.handle_left), right=list(p.handle_right),
                     lt=p.handle_left_type, rt=p.handle_right_type, interpolation=p.interpolation,
                     type=p.type, easing=p.easing, amplitude=p.amplitude, back=p.back, period=p.period)
                 for p in c.keyframe_points] for key,c in _curves(action).items()}


def restore(action, state):
    curves = _curves(action)
    if set(curves) != set(state):
        raise RuntimeError('接缝动作通道已改变，无法安全恢复成对备份')
    for key,rows in state.items():
        c = curves[key]
        c.keyframe_points.clear()
        c.keyframe_points.add(len(rows))
        for p,row in zip(c.keyframe_points,rows):
            p.co = row['co']
        c.update()
        for p,row in zip(c.keyframe_points,rows):
            p.handle_left_type, p.handle_right_type = row['lt'],row['rt']
            p.interpolation,p.type,p.easing = row['interpolation'],row['type'],row['easing']
            p.amplitude,p.back,p.period = row['amplitude'],row['back'],row['period']
            p.handle_left,p.handle_right = row['left'],row['right']
    action.update_tag()


def digest(action, left, right):
    rows = [(key,[p for p in value if left <= p['co'][0] <= right])
            for key,value in sorted(snapshot(action).items())]
    return hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()


def _backup(action, suffix):
    copy = action.copy()
    copy.name = action.name + suffix
    copy['bam_role'] = 'SEAM_PAIR_BASELINE'
    copy.use_fake_user = True
    return copy


def _exclusive(action, target):
    for obj in bpy.data.objects:
        ad = getattr(obj,'animation_data',None)
        if obj != target and ad is not None and (ad.action == action or any(
                strip.action == action for track in ad.nla_tracks for strip in track.strips)):
            raise RuntimeError('前段 Action 正被其他模型共用，已停止以免改变其他模型')


class Transaction:
    def __init__(self, previous, selected, target):
        self.previous = previous
        self.before = snapshot(previous) if previous is not None else None
        self.created = []
        self.done = False
        from .auto_director import _is_retarget_output_action
        if selected is not None and selected.get('bam_target_object') == target.name:
            ad = target.animation_data
            live = [ad.action] + [strip.action for track in ad.nla_tracks for strip in track.strips]
            if any(other is not None and other != selected and _is_retarget_output_action(other)
                   and other.get('baw_seam_pair_previous') == selected.name for other in live):
                raise RuntimeError('本段末尾已参与下一接缝均分；请先在后一段关闭防突变并重新映射以恢复成对动作')
            if previous is None and selected.get('baw_seam_pair_previous'):
                raise RuntimeError('原均分接缝的前段已不相邻，无法安全恢复配对动作')
        # A source-model pair must never restore/modify the destination model.
        if (previous is None or selected is None
                or selected.get('bam_target_object') != target.name
                or not selected.get('baw_seam_pair_previous')):
            return
        _exclusive(previous,target)
        backup = bpy.data.actions.get(selected.get('baw_seam_pair_previous_baseline',''))
        if backup is None or selected['baw_seam_pair_previous'] != previous.name:
            raise RuntimeError('找不到原接缝的前段配对备份，已停止，未叠加修正')
        left,right = selected['baw_seam_pair_left'],selected['baw_seam_pair_boundary']
        if digest(previous,left,right) != selected.get('baw_seam_pair_digest'):
            raise RuntimeError('前段接缝窗口在上次修正后被编辑，已停止以保护修改；请先确认该接缝')
        original = snapshot(backup)
        if set(original) != set(self.before):
            raise RuntimeError('前段动作通道已改变，不能自动撤回旧接缝修正')
        merged = {key:sorted([p for p in rows if not left <= p['co'][0] <= right]
                            +[p for p in original[key] if left <= p['co'][0] <= right],key=lambda p:p['co'][0])
                  for key,rows in self.before.items()}
        restore(previous,merged)

    def rollback(self):
        if self.done:
            return
        if self.previous is not None and self.before is not None:
            restore(self.previous,self.before)
        for action in self.created:
            bpy.data.actions.remove(action)
        self.created.clear()

    def commit(self):
        self.done = True

    def apply(self, scene, target, action, start, end, total):
        from .auto_director import _action_bone_channels, _clip_motion_bounds
        previous = self.previous
        action['baw_seam_smoothing_enabled'] = False
        if previous is None or _clip_motion_bounds(previous)[1] != start:
            action['baw_seam_smoothing_status'] = 'NO_ADJACENT_CLIP'
            return False
        # Total is the full window, not the duration of each half. Odd frame
        # goes to the current clip; shorten both sides together for short clips.
        pstart,_ = _clip_motion_bounds(previous)
        effective = min(int(total),2*(start-pstart),2*(end-start)+1)
        left_count,right_count = effective//2,effective-effective//2
        if min(left_count,right_count)<2:
            action['baw_seam_smoothing_status']='CLIP_TOO_SHORT'
            return False
        left,right = start-left_count,start+right_count
        _exclusive(previous,target)
        # Do not touch a previous clip's already-smoothed head with its tail.
        old_report = json.loads(previous.get('baw_seam_smoothing_report','{}'))
        if old_report.get('release',pstart) > left:
            raise RuntimeError('前后接缝过渡窗口重叠，请缩短总过渡帧数')
        paths0,paths1 = _action_bone_channels(previous),_action_bone_channels(action)
        names = {n:paths0[n] & paths1[n] for n in paths0.keys() & paths1.keys()}
        if not names:
            action['baw_seam_smoothing_status']='NO_COMMON_CHANNELS'
            return False
        before_prev,before_new = snapshot(previous),snapshot(action)
        pbackup = _backup(previous,'_前后均分_前段原版')
        nbackup = _backup(action,'_前后均分_后段原版')
        self.created.extend([pbackup,nbackup])
        ad = target.animation_data
        saved = ad.action,ad.use_nla,scene.frame_current,getattr(ad,'action_slot',None)
        try:
            ad.use_nla=False
            def sample(act,f):
                ad.action=act; scene.frame_set(f); bpy.context.view_layer.update()
                out={}
                for n in names:
                    b=target.pose.bones[n]
                    loc,q,scale=b.matrix_basis.decompose()
                    if b.rotation_mode=='QUATERNION' and q.dot(b.rotation_quaternion)<0:
                        q.negate()
                    out[n]=loc,q,scale
                return out
            a0,a1=sample(previous,left),sample(previous,left+1)
            b0,b1=sample(action,right-1),sample(action,right)
            span=right-left-2
            from .seam_smoothing import _unit_shortest
            values={}
            for f in range(left+2,right-1):
                t=(f-left-1)/span
                h00=2*t**3-3*t*t+1; h10=t**3-2*t*t+t
                h01=-2*t**3+3*t*t; h11=t**3-t*t
                values[f]={}
                for n in names:
                    l0,q0,s0=a0[n]; l1,q1,s1=a1[n]
                    r0,p0,z0=b0[n]; r1,p1,z1=b1[n]
                    loc=h00*l1+h10*span*(l1-l0)+h01*r0+h11*span*(r1-r0)
                    v0=_unit_shortest(q0.inverted() @ q1)
                    v1=_unit_shortest(p0.inverted() @ p1)
                    controls=[q1,q1 @ _step(v0,span/3),
                              p0 @ _step(v1,-span/3),p0]
                    for _ in range(3):
                        controls=[x.slerp(y,t) for x,y in zip(controls,controls[1:])]
                    scale=s1.lerp(z0,t*t*(3-2*t))
                    values[f][n]=loc,controls[0].normalized(),scale
            for dest,lo,hi,original in ((previous,left,start,before_prev),(action,start,right,before_new)):
                ad.action=dest
                last={}
                for f in range(lo,hi+1):
                    if f not in values:
                        continue
                    scene.frame_set(f)
                    for n,paths in names.items():
                        bone=target.pose.bones[n]; loc,q,scale=values[f][n]
                        if 'location' in paths:
                            bone.location=loc; bone.keyframe_insert('location',frame=f,group=n)
                        if 'scale' in paths:
                            bone.scale=scale; bone.keyframe_insert('scale',frame=f,group=n)
                        if 'rotation_quaternion' in paths:
                            q=q.copy()
                            if q.dot(last.get(n,bone.rotation_quaternion))<0: q.negate()
                            bone.rotation_quaternion=q; last[n]=q.copy(); prop='rotation_quaternion'
                        elif 'rotation_euler' in paths:
                            q=q.to_euler(bone.rotation_mode)
                            q.make_compatible(last.get(n,bone.rotation_euler))
                            bone.rotation_euler=q; last[n]=q.copy(); prop='rotation_euler'
                        elif 'rotation_axis_angle' in paths:
                            q=_unit_shortest(q); bone.rotation_axis_angle=(q.angle,*q.axis); prop='rotation_axis_angle'
                        else:
                            continue
                        bone.keyframe_insert(prop,frame=f,group=n)
                    bpy.context.view_layer.update()
                # Preserve all outside/anchor values and handles exactly.
                current=snapshot(dest)
                owned={target.pose.bones[n].path_from_id(p) for n,paths in names.items() for p in paths}
                for key,rows in current.items():
                    priors={p['co'][0]:p for p in original[key]}
                    for i,p in enumerate(rows):
                        f=p['co'][0]
                        if key[0] in owned and left+1 <= f < right-1:
                            p['interpolation']='LINEAR'
                        if not left+1 <= f < right-1 and f in priors:
                            rows[i]=priors[f]
                restore(dest,current)
            action['baw_seam_smoothing_enabled']=True
            action['baw_seam_smoothing_status']='APPLIED'
            action['baw_seam_smoothing_baseline']=nbackup.name
            action['baw_seam_pair_previous']=previous.name
            action['baw_seam_pair_previous_baseline']=pbackup.name
            action['baw_seam_pair_left']=left
            action['baw_seam_pair_boundary']=start
            action['baw_seam_pair_digest']=digest(previous,left,start)
            action['baw_seam_smoothing_report']=json.dumps(dict(mode='SPLIT',start=start,
                left=left,release=right,frames=effective,before_frames=left_count,after_frames=right_count,
                previous=previous.name,bones=len(names)),ensure_ascii=False)
            return True
        finally:
            ad.action,ad.use_nla=saved[:2]
            if saved[0] is not None and saved[3] is not None: ad.action_slot=saved[3]
            scene.frame_set(saved[2])
