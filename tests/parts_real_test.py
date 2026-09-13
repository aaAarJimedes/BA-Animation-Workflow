"""Read-only source model regression; output stays in the task temp directory."""
import sys,json,hashlib
from pathlib import Path
import bpy
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'extension'))
import ba_animation_workflow as addon
addon.register()
from ba_animation_workflow import parts,parts_ui
out=Path('D:/Agent Workspaces/Agent Temp/BA_Animation_Workflow/testing/parts')
out.mkdir(parents=True,exist_ok=True)
source=Path('D:/Agent Workspaces/Agent Delivery/Mama_Animation/Character/AvatarBuilder发骨优化/伊落玛丽-AvatarBuilder柔顺发骨.blend')
original_hash=hashlib.sha256(source.read_bytes()).hexdigest()
bpy.ops.wm.open_mainfile(filepath=str(source),load_ui=False,use_scripts=False)
r=next(o for o in bpy.data.objects if o.type=='ARMATURE');obj=next(o for o in bpy.data.objects if o.type=='MESH' and o.find_armature()==r)
scene=bpy.context.scene;s=scene.baw_parts;s.target=obj
state=(scene.render.fps,scene.frame_start,scene.frame_end,scene.frame_current,len(bpy.data.actions),scene.rigidbody_world.point_cache.is_baked)
sig=parts.fingerprint(obj);key=obj.data.shape_keys;oldmat=[x.material for x in obj.material_slots]
assert bpy.ops.baw.parts_analyze()=={'FINISHED'}
groups={p.group_id:{'name':p.label,'faces':p.faces,'review':p.review} for p in s.groups}
assert all(groups[i]['faces']>0 for i in [1,2,3,4,5])
assert bpy.ops.baw.parts_preview()=={'FINISHED'}
assert s.preview and obj.hide_viewport and not obj.hide_render
assert [x.material for x in obj.material_slots]==oldmat
assert bpy.ops.baw.parts_preview()=={'FINISHED'}
assert not obj.hide_get() and not s.preview
assert bpy.ops.baw.parts_extract()=={'FINISHED'}
assert s.result and s.result.get('baw_parts_verified') and obj.hide_render
objects=list(s.result.all_objects)
assert len(objects)==4,[(o.name,len(o.data.polygons)) for o in objects]
assert parts.fingerprint(obj)==sig
assert len(key.key_blocks)==65
assert bpy.ops.baw.parts_switch()=={'FINISHED'}
assert not obj.hide_render and all(o.hide_render for o in objects)
assert bpy.ops.baw.parts_switch()=={'FINISHED'}
result_file=out/'玛丽-部件分离验证.blend'
bpy.context.preferences.filepaths.save_version=0
bpy.ops.wm.save_as_mainfile(filepath=str(result_file),compress=True)
bpy.ops.wm.open_mainfile(filepath=str(result_file),load_ui=False,use_scripts=False)
scene=bpy.context.scene;s=scene.baw_parts
assert len(s.sources)==1 and s.result and s.showing_result
for piece in list(s.result.all_objects): parts.verify_piece(s.sources[0].object,piece)
assert bpy.ops.baw.parts_preview()=={'FINISHED'}
assert all(o.hide_viewport and o.hide_render for o in list(s.result.all_objects))
assert bpy.ops.baw.parts_preview()=={'FINISHED'}
assert state==(scene.render.fps,scene.frame_start,scene.frame_end,scene.frame_current,len(bpy.data.actions),scene.rigidbody_world.point_cache.is_baked)
assert hashlib.sha256(source.read_bytes()).hexdigest()==original_hash
report={'source_untouched':True,'groups':groups,'results':[(o.name,len(o.data.polygons),len(o.data.shape_keys.key_blocks)) for o in s.result.all_objects],'save_reopen':True,'preview_and_switch':True,'full_geometry_shape_uv_weight_material_checks':True,'custom_normal_max_vector_error':max(o.get('baw_part_normal_max_error',0) for o in s.result.all_objects),'fps_and_physics_unchanged':True}
(out/'real_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print('PARTS_REAL_OK',json.dumps(report,ensure_ascii=False))
