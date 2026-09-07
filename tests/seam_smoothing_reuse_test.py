"""Real clip seam A/B, prior protection, window isolation and option interplay."""
import bpy, importlib, os, json, math
a=importlib.import_module(os.environ.get('BAW_AUTO_ADDON_MODULE','ba_animation_workflow')+'.auto_director')
s=bpy.context.scene; cfg=s.baw_auto_director; target=cfg.reuse_target_rig or cfg.target_rig
cfg.reuse_target_rig=target
cfg.remap_prompt_text=bpy.data.texts[os.environ.get('BAW_SEAM_TEXT','第九段')]
selected=cfg.remap_action
start,end=a._clip_motion_bounds(selected)
previous=a._find_previous_target_action(target,selected,start)
assert previous is not None
def keys(action, predicate=lambda f:True):
    return [(c.data_path,c.array_index,[(tuple(k.co),tuple(k.handle_left),tuple(k.handle_right),k.interpolation) for k in c.keyframe_points if predicate(k.co.x)]) for c in a._iter_action_fcurves(action)]
protected={x.name:keys(x) for x in bpy.data.actions if a._is_retarget_output_action(x) and a._clip_motion_bounds(x)!=(start,end)}
def sample(action,frame):
    ad=target.animation_data
    before=ad.action,ad.use_nla
    ad.action=action; ad.use_nla=False
    s.frame_set(frame); bpy.context.view_layer.update()
    out={b.name:b.matrix_basis.decompose() for b in target.pose.bones}
    ad.action,ad.use_nla=before
    return out
assert not cfg.bl_rna.properties['reuse_seam_smoothing'].default
cfg.reuse_foot_contact=os.environ.get('BAW_SEAM_WITH_FEET')=='1'
cfg.reuse_seam_smoothing=True
cfg.reuse_seam_frames=10
assert bpy.ops.baw.auto_remap_existing('EXEC_DEFAULT')=={'FINISHED'},cfg.status_message
result=cfg.remap_action
assert result.get('baw_seam_smoothing_enabled')
baseline=bpy.data.actions[result['baw_seam_smoothing_baseline']]
assert not a._is_retarget_output_action(baseline)
report=json.loads(result['baw_seam_smoothing_report'])
assert keys(baseline,lambda f:f>=report['release']-1 or f<start)==keys(result,lambda f:f>=report['release']-1 or f<start),'outside-window keys/handles changed'
for name,value in protected.items():
    assert name in bpy.data.actions and keys(bpy.data.actions[name])==value,('previous or later clip modified',name)
p0=sample(previous,start-1); p1=sample(previous,start)
off0=sample(baseline,start); off1=sample(baseline,start+1)
on0=sample(result,start); on1=sample(result,start+1)
def angle(q):
    return math.degrees(2*math.acos(min(1.,abs(q.normalized().w))))
metrics={'before_degrees':0.,'after_degrees':0.,'pose_error_degrees':0.,'velocity_location_error':0.}
channels=a._action_bone_channels(result)
prev_channels=a._action_bone_channels(previous)
for n in channels.keys() & prev_channels.keys():
    paths=channels[n] & prev_channels[n]
    if paths & {'rotation_quaternion','rotation_euler','rotation_axis_angle'}:
        velocity=p0[n][1].inverted() @ p1[n][1]
        for label,s0,s1 in [('before_degrees',off0,off1),('after_degrees',on0,on1)]:
            diff=velocity.inverted() @ s0[n][1].inverted() @ s1[n][1]
            metrics[label]=max(metrics[label],angle(diff))
        metrics['pose_error_degrees']=max(metrics['pose_error_degrees'],angle(p1[n][1].inverted() @ on0[n][1]))
    if 'location' in paths:
        metrics['velocity_location_error']=max(metrics['velocity_location_error'],(on1[n][0]-on0[n][0]-(p1[n][0]-p0[n][0])).length)
assert metrics['after_degrees']<.1,metrics
assert metrics['pose_error_degrees']<.1,metrics
assert metrics['velocity_location_error']<1e-5,metrics
# The last two samples are the exact baseline, so no new jump at release.
for f in [report['release']-1,report['release'],end]:
    off=sample(baseline,f); on=sample(result,f)
    for n in channels:
        assert (off[n][0]-on[n][0]).length<1e-5
        assert angle(off[n][1].inverted() @ on[n][1])<.1
cfg.reuse_seam_smoothing=False
assert bpy.ops.baw.auto_remap_existing('EXEC_DEFAULT')=={'FINISHED'}
assert not cfg.remap_action.get('baw_seam_smoothing_enabled')
for f in range(start,end+1):
    off=sample(baseline,f); restored=sample(cfg.remap_action,f)
    for n in channels:
        assert angle(off[n][1].inverted() @ restored[n][1])<.1
        assert (off[n][0]-restored[n][0]).length<1e-4
print('SEAM_SMOOTHING_REUSE_PASS',json.dumps(dict(metrics,foot_contact=cfg.reuse_foot_contact,other_clips_unchanged=True,outside_window_unchanged=True,off_restores_baseline=True,saved=False)))
