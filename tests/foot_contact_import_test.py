"""Single accepted clip reuse into a disposable new rig, with contact on."""
import bpy, importlib, os, json
from mathutils import Vector
a=importlib.import_module(os.environ.get('BAW_AUTO_ADDON_MODULE','ba_animation_workflow')+'.auto_director')
contact=importlib.import_module(a.__package__+'.foot_contact')
s=bpy.context.scene; cfg=s.baw_auto_director
old=cfg.reuse_target_rig or cfg.target_rig
old_action=old.animation_data.action
selected=a._resolve_text_action(s,cfg,bpy.data.texts['第八段'],target=old)
old_keys={x.name:[[(tuple(k.co)) for k in c.keyframe_points] for c in a._iter_action_fcurves(x)] for x in bpy.data.actions if a._is_retarget_output_action(x)}
new=old.copy(); new.data=old.data.copy(); new.animation_data_clear()
s.collection.objects.link(new)
cfg.reuse_target_rig=new
cfg.remap_action=selected
cfg.reuse_foot_contact=True
assert bpy.ops.baw.auto_import_existing('EXEC_DEFAULT',action_name=selected.name)=={'FINISHED'},cfg.status_message
output=cfg.remap_action
assert output.get('baw_foot_contact_enabled')
assert output.get('bam_target_object')==new.name
assert a._clip_motion_bounds(output)==a._clip_motion_bounds(selected)
assert old.animation_data.action==old_action
for name,keys in old_keys.items():
    assert keys==[[(tuple(k.co)) for k in c.keyframe_points] for c in a._iter_action_fcurves(bpy.data.actions[name])]
assert contact.contact_ranges([Vector((0,0,0)) for _ in range(30)],1,24,0)==[(0,29)]
assert not contact.contact_ranges([Vector((0,0,.3)) for _ in range(30)],1,24,0)
assert not contact.contact_ranges([Vector((i*.01,0,0)) for i in range(30)],1,24,0)
assert not contact.contact_ranges([Vector((i*.001,0,0)) for i in range(100)],1,24,0)
print('FOOT_CONTACT_IMPORT_PASS',json.dumps({'saved':False,'old_model_unchanged':True,'lifted_and_moving_feet_not_locked':True,'report':output['baw_foot_contact_report']},ensure_ascii=False))
