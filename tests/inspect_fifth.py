import bpy, json, importlib, os
a = importlib.import_module(os.environ.get('BAW_AUTO_ADDON_MODULE','ba_animation_workflow')+'.auto_director')
s=bpy.context.scene
t=s.baw_auto_director.target_rig or s.baw_auto_director.reuse_target_rig
print('FIFTH_STATE',json.dumps({'target':t.name,'frame':s.frame_current,'texts':[(x.name,x.as_string()[:200]) for x in bpy.data.texts if '段' in x.name],'actions':[(x.name,list(x.frame_range),x.get('baw_prompt_text'),x.get('baw_source_action')) for x in bpy.data.actions if x.get('bam_target_object')==t.name or x.name.startswith('Proscenium_Motion:')],'blocks':[(b.prompt,b.frame_start,b.frame_end) for b in s.proscenium.prompt_blocks] if hasattr(s,'proscenium') else []},ensure_ascii=False))
act=t.animation_data.action
print('ACTIVE',act.name,dict(act.items()))
for f in [342,343,350,370,390,420]:
 s.frame_set(f); bpy.context.view_layer.update()
 print('POSE',f,[(b.name,tuple(round(v,4) for v in b.matrix_basis.to_euler()),tuple(round(v,4) for v in b.matrix.to_euler())) for b in t.pose.bones if b.name in ['センター','グルーブ','下半身','上半身','上半身2']])
