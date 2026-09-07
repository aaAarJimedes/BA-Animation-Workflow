"""New-model two-clip reuse; skip absent predecessor, then smooth next clip."""
import bpy, importlib, os, json
a=importlib.import_module(os.environ.get('BAW_AUTO_ADDON_MODULE','ba_animation_workflow')+'.auto_director')
ss=importlib.import_module(a.__package__+'.seam_smoothing')
s=bpy.context.scene; cfg=s.baw_auto_director; old=cfg.reuse_target_rig or cfg.target_rig
selected=[a._resolve_text_action(s,cfg,bpy.data.texts[n],target=old) for n in ('第八段','第九段')]
old_active=old.animation_data.action
new=old.copy(); new.data=old.data.copy(); new.animation_data_clear(); s.collection.objects.link(new)
cfg.reuse_target_rig=new; cfg.reuse_foot_contact=False; cfg.reuse_seam_smoothing=True
cfg.reuse_seam_frames=10
first,_=a._import_linked_action(bpy.context,cfg,selected[0],new)
assert first.get('baw_seam_smoothing_status')=='NO_ADJACENT_CLIP'
def keys(act):
    return [[tuple(k.co) for k in c.keyframe_points] for c in a._iter_action_fcurves(act)]
before=keys(first)
second,_=a._import_linked_action(bpy.context,cfg,selected[1],new,previous=first)
assert second.get('baw_seam_smoothing_enabled')
assert before==keys(first)
assert old.animation_data.action==old_active
tmp=second.copy()
assert not ss.apply(s,new,tmp,first,668,670,10)
assert tmp.get('baw_seam_smoothing_status')=='CLIP_TOO_SHORT'
bpy.data.actions.remove(tmp)
print('SEAM_SMOOTHING_IMPORT_PASS: no prior/short clip skip; second clip applied; old model and first clip unchanged; no save')
