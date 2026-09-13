import bpy,sys
from pathlib import Path
from mathutils import Vector
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'extension'))
import ba_animation_workflow as addon
addon.register()
out=Path('D:/Agent Workspaces/Agent Temp/BA_Animation_Workflow/testing/parts')
bpy.ops.wm.open_mainfile(filepath=str(out/'玛丽-部件分离验证.blend'),load_ui=False,use_scripts=False)
s=bpy.context.scene
settings=s.baw_parts
textured='--textured' in sys.argv
if textured:
 from ba_animation_workflow.parts_ui import show_original
 show_original(bpy.context,settings)
else:
 assert bpy.ops.baw.parts_preview()=={'FINISHED'}
 for source in settings.sources:source.object.hide_render=True
 for obj in settings.preview.objects:obj.hide_render=False
 print('PREVIEW_MATERIALS',[(o.name,[(m.name,tuple(m.diffuse_color),sum(p.material_index==i for p in o.data.polygons)) for i,m in enumerate(o.data.materials)],o.hide_render,o.hide_viewport) for o in settings.preview.objects])
 print('PREVIEW_SLOTS',[(o.name,[(s.link,s.material.name if s.material else None) for s in o.material_slots]) for o in settings.preview.objects])
 print('VISIBLE_MESHES',[(o.name,o.hide_render,o.hide_viewport,o.hide_get()) for o in s.objects if o.type=='MESH' and o.find_armature()])
camd=bpy.data.cameras.new('QA');cam=bpy.data.objects.new('QA',camd);s.collection.objects.link(cam)
cam.location=(.8,4.3,1.25);cam.rotation_euler=(Vector((.5,1.18,.87))-cam.location).to_track_quat('-Z','Y').to_euler();camd.type='ORTHO';camd.ortho_scale=1.94;s.camera=cam
s.render.engine='BLENDER_WORKBENCH';s.render.resolution_x=650;s.render.resolution_y=950;s.render.resolution_percentage=100
s.display.shading.light='STUDIO';s.display.shading.color_type='MATERIAL';s.display.shading.show_cavity=True;s.display.shading.background_type='WORLD';s.world.color=(.09,.09,.09)
if textured:s.display.shading.color_type='TEXTURE'
s.view_settings.view_transform='Standard';s.view_settings.look='None';s.view_settings.exposure=0;s.view_settings.gamma=1
s.render.image_settings.file_format='PNG';s.render.filepath=str(out/('原材质部件参考.png' if textured else '部件识别预览.png'));bpy.ops.render.render(write_still=True)
print('PARTS_RENDER_OK')
