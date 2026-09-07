"""Real clip A/B test in disposable background Blender memory."""
import bpy, importlib, json, os
from mathutils import Vector
a=importlib.import_module(os.environ.get('BAW_AUTO_ADDON_MODULE','ba_animation_workflow')+'.auto_director')
s=bpy.context.scene; cfg=s.baw_auto_director
t=cfg.reuse_target_rig or cfg.target_rig
cfg.reuse_target_rig=t
cfg.remap_prompt_text=bpy.data.texts.get(os.environ.get('BAW_CONTACT_TEXT','第八段'))
selected=cfg.remap_action
start,end=a._clip_motion_bounds(selected)
def keys(action):
    return [(c.data_path,c.array_index,[tuple(p.co) for p in c.keyframe_points]) for c in a._iter_action_fcurves(action)]
protected={x.name:keys(x) for x in bpy.data.actions if a._is_retarget_output_action(x) and a._clip_motion_bounds(x)!=(start,end)}
def sample(action):
    ad=t.animation_data; before=ad.action,ad.use_nla
    ad.action=action; ad.use_nla=False
    pts={name:[] for name in ['足首.L','足首.R']}
    for f in range(start,end+1):
        s.frame_set(f); bpy.context.view_layer.update()
        ev=t.evaluated_get(bpy.context.evaluated_depsgraph_get())
        for n in pts:
            pts[n].append((ev.matrix_world @ ev.pose.bones[n].head).copy())
    ad.action,ad.use_nla=before
    return pts
assert not cfg.bl_rna.properties['reuse_foot_contact'].default
cfg.reuse_foot_contact=True
assert bpy.ops.baw.auto_remap_existing('EXEC_DEFAULT',action_name=selected.name)=={'FINISHED'},cfg.status_message
corrected=cfg.remap_action
assert corrected.get('baw_foot_contact_enabled')
baseline=bpy.data.actions[corrected['baw_foot_contact_baseline']]
assert not a._is_retarget_output_action(baseline)
report=json.loads(corrected['baw_foot_contact_report'])
off=sample(baseline); on=sample(corrected)
metrics={}
for n in off:
    def span(points):
        return max((p-q).length for p in points for q in points)
    metrics[n]={'off_span':span(off[n][8:-6]),'on_span':span(on[n][8:-6]),'seam_error':(off[n][0]-on[n][0]).length}
    assert metrics[n]['seam_error']<1e-4
    if os.environ.get('BAW_CONTACT_TEXT','第八段')=='第八段':
        assert metrics[n]['on_span'] < metrics[n]['off_span']*.35,metrics
for name,value in protected.items():
    assert name in bpy.data.actions and keys(bpy.data.actions[name])==value,('changed other clip',name)
# In source swing frames, the bake must leave all leg local rotations intact.
ad=t.animation_data
for n,runs in report['ranges'].items():
    chain=[n.replace('足首','足'),n.replace('足首','ひざ'),n]
    for f in range(start,end+1):
        if any(lo<=f<=hi for lo,hi in runs):
            continue
        rotations=[]
        for action in (baseline,corrected):
            ad.action=action; ad.use_nla=False
            s.frame_set(f); bpy.context.view_layer.update()
            rotations.append([t.pose.bones[b].matrix_basis.to_quaternion() for b in chain])
        assert all(abs(x.dot(y))>1-1e-5 for x,y in zip(*rotations)),('swing modified',n,f)
ad.action=corrected; ad.use_nla=True
# OFF always rebakes from clean source, not from corrected/backup keys.
cfg.reuse_foot_contact=False
baseline_keys=keys(baseline)
assert bpy.ops.baw.auto_remap_existing('EXEC_DEFAULT',action_name=corrected.name)=={'FINISHED'}
assert not cfg.remap_action.get('baw_foot_contact_enabled',False)
restored=sample(cfg.remap_action)
off_error=max((restored[n][i]-off[n][i]).length for n in off for i in range(len(off[n])))
assert off_error<1e-4,('OFF did not reproduce raw reuse output',off_error)
print('FOOT_CONTACT_REUSE_PASS',json.dumps({'metrics':metrics,'report':report,'other_clips_unchanged':True,'off_restores_baseline':True,'saved':False},ensure_ascii=False))
