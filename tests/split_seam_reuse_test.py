"""Pair blending, idempotence, mode switch, guarded restore and rollback."""
import bpy, importlib, os, json, math
a=importlib.import_module(os.environ.get('BAW_AUTO_ADDON_MODULE','ba_animation_workflow')+'.auto_director')
split=importlib.import_module(a.__package__+'.split_seam')
s=bpy.context.scene; cfg=s.baw_auto_director; target=cfg.reuse_target_rig or cfg.target_rig
cfg.reuse_target_rig=target; cfg.remap_prompt_text=bpy.data.texts['第九段']
selected=cfg.remap_action; start,end=a._clip_motion_bounds(selected)
previous=a._find_previous_target_action(target,selected,start)
assert previous is not None
prev_original=split.snapshot(previous)
others={x.name:split.snapshot(x) for x in bpy.data.actions if a._is_retarget_output_action(x) and x not in (previous,selected)}
cfg.reuse_foot_contact=False; cfg.reuse_seam_smoothing=True; cfg.reuse_seam_mode='SPLIT'; cfg.reuse_seam_frames=10
def run():
    assert bpy.ops.baw.auto_remap_existing('EXEC_DEFAULT')=={'FINISHED'},cfg.status_message
    return cfg.remap_action
result=run()
report=json.loads(result['baw_seam_smoothing_report'])
assert report['before_frames']==5 and report['after_frames']==5
left,right=report['left'],report['release']
def outside(state,lo,hi):
    return {key:[p for p in rows if p['co'][0]<lo or p['co'][0]>hi] for key,rows in state.items()}
assert split.snapshot(previous)!=prev_original
assert outside(split.snapshot(previous),left,start)==outside(prev_original,left,start)
raw=bpy.data.actions[result['baw_seam_smoothing_baseline']]
original_previous=bpy.data.actions[result['baw_seam_pair_previous_baseline']]
assert outside(split.snapshot(result),start,right)==outside(split.snapshot(raw),start,right)
def pose(act,f):
    ad=target.animation_data; saved=ad.action,ad.use_nla
    ad.action=act; ad.use_nla=False; s.frame_set(f); bpy.context.view_layer.update()
    rows={n:target.pose.bones[n].matrix_basis.decompose() for n in a._action_bone_channels(act)}
    ad.action,ad.use_nla=saved
    return rows
p=pose(previous,start); q=pose(result,start)
pose_error=max((p[n][0]-q[n][0]).length for n in p.keys() & q.keys())
rotation_error=max(1-abs(p[n][1].dot(q[n][1])) for n in p.keys() & q.keys())
assert pose_error<1e-5 and rotation_error<1e-5,(pose_error,rotation_error)
def velocity_jump(prev,cur):
    p0,p1=pose(prev,start-1),pose(prev,start)
    q0,q1=pose(cur,start),pose(cur,start+1)
    maximum=0.
    for n in p0.keys() & q0.keys():
        diff=(p0[n][1].inverted() @ p1[n][1]).inverted() @ (q0[n][1].inverted() @ q1[n][1])
        maximum=max(maximum,math.degrees(2*math.atan2(math.sqrt(diff.x**2+diff.y**2+diff.z**2),abs(diff.w))))
    return maximum
jump_before=velocity_jump(original_previous,raw)
jump_after=velocity_jump(previous,result)
assert jump_after<jump_before,(jump_before,jump_after)
for name,state in others.items():
    assert split.snapshot(bpy.data.actions[name])==state,('unrelated clip changed',name)
pair_first=split.snapshot(previous)
poses_first={f:pose(result,f) for f in range(start,right+1)}
result=run()
pair_second=split.snapshot(previous)
repeat_error=max(abs(x-y) for key,rows in pair_first.items() for old,new in zip(rows,pair_second[key]) for field in ('co','left','right') for x,y in zip(old[field],new[field]))
assert repeat_error<1e-5,('previous tail accumulated corrections',repeat_error)
for f,old in poses_first.items():
    new=pose(result,f)
    assert max((old[n][0]-new[n][0]).length for n in old)<1e-5
    assert max(1-abs(old[n][1].dot(new[n][1])) for n in old)<1e-5
# Switching mode must undo the old previous-tail edit before capturing its pose.
cfg.reuse_seam_mode='CURRENT'; result=run()
assert split.snapshot(previous)==prev_original,'single-sided mode did not restore previous tail'
cfg.reuse_seam_mode='SPLIT'; cfg.reuse_seam_frames=11; result=run()
r=json.loads(result['baw_seam_smoothing_report'])
assert (r['before_frames'],r['after_frames'])==(5,6)
cfg.reuse_seam_smoothing=False; result=run()
assert split.snapshot(previous)==prev_original,'OFF did not restore the pair'
cfg.reuse_seam_smoothing=True; cfg.reuse_seam_mode='SPLIT'; result=run()
pre_failure=split.snapshot(previous)
old_apply=split.Transaction.apply
def failure(self,*args,**kwargs):
    old_apply(self,*args,**kwargs)
    raise RuntimeError('Injected pair failure')
split.Transaction.apply=failure
try:
    bpy.ops.baw.auto_remap_existing('EXEC_DEFAULT')
    raise AssertionError('injected failure was accepted')
except RuntimeError as exc:
    assert 'Injected pair failure' in str(exc)
finally:
    split.Transaction.apply=old_apply
assert split.snapshot(previous)==pre_failure,'failed remap left previous modified'
# Manual edits in the owned window must be protected, not silently undone.
curve=next(iter(split._curves(previous).values()))
point=next(p for p in curve.keyframe_points if left+1<p.co.x<start)
point.co.y+=.0123
manual=split.snapshot(previous)
try:
    bpy.ops.baw.auto_remap_existing('EXEC_DEFAULT')
    raise AssertionError('manual edit guard did not stop remap')
except RuntimeError as exc:
    assert '被编辑' in str(exc)
assert split.snapshot(previous)==manual
print('SPLIT_SEAM_REUSE_PASS',json.dumps(dict(left=left,boundary=start,right=right,jump_before=jump_before,jump_after=jump_after,pose_error=pose_error,rotation_error=rotation_error,repeat_error=repeat_error,idempotent=True,off_restores_previous=True,rollback=True,manual_edit_guard=True,saved=False)))
