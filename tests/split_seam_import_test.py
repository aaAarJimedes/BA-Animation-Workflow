import bpy, importlib, os, json
a=importlib.import_module(os.environ.get('BAW_AUTO_ADDON_MODULE','ba_animation_workflow')+'.auto_director')
split=importlib.import_module(a.__package__+'.split_seam')
s=bpy.context.scene; cfg=s.baw_auto_director; old=cfg.reuse_target_rig or cfg.target_rig
clips=[a._resolve_text_action(s,cfg,bpy.data.texts[n],target=old) for n in ('第八段','第九段')]
protected={c.name:split.snapshot(c) for c in clips}
new=old.copy(); new.data=old.data.copy(); new.animation_data_clear(); s.collection.objects.link(new)
cfg.reuse_target_rig=new; cfg.reuse_foot_contact=False
cfg.reuse_seam_smoothing=True; cfg.reuse_seam_mode='SPLIT'; cfg.reuse_seam_frames=10
first,_=a._import_linked_action(bpy.context,cfg,clips[0],new)
assert first.get('baw_seam_smoothing_status')=='NO_ADJACENT_CLIP'
before=split.snapshot(first)
second,_=a._import_linked_action(bpy.context,cfg,clips[1],new,previous=first)
assert second.get('baw_seam_pair_previous')==first.name
assert before!=split.snapshot(first)
assert before==split.snapshot(bpy.data.actions[second['baw_seam_pair_previous_baseline']])
for name,state in protected.items():
    assert split.snapshot(bpy.data.actions[name])==state
cfg.remap_action=second
cfg.reuse_seam_smoothing=False
assert bpy.ops.baw.auto_remap_existing('EXEC_DEFAULT')=={'FINISHED'}
assert before==split.snapshot(first)
print('SPLIT_SEAM_IMPORT_PASS: new model pair and restore work; source model untouched; no save')
