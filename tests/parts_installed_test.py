import bpy,json,hashlib,tomllib,importlib
from pathlib import Path
module='bl_ext.user_default.ba_animation_workflow'
assert module in bpy.context.preferences.addons,'Installed extension is not enabled'
m=importlib.import_module(module);base=Path(m.__file__).parent
manifest=json.loads(Path('D:/Agent Workspaces/Agent Delivery/BA_Animation_Workflow/releases/0.13.0/build-manifest.json').read_text())
assert tomllib.loads((base/'blender_manifest.toml').read_text(encoding='utf8'))['version']=='0.13.0'
for name,digest in manifest['source_files'].items():
 assert hashlib.sha256((base/name).read_bytes()).hexdigest()==digest,name
for name in ['parts_analyze','parts_preview','parts_select','parts_assign','parts_extract','parts_switch','inspect_assets','physics_bake','export_render_plan']:
 assert getattr(bpy.ops.baw,name).get_rna_type(),name
assert tuple(m.constants.ADDON_VERSION)==(0,13,0)
# Exercise the installed operator, not only registration or on-disk file copies.
bpy.ops.mesh.primitive_cube_add();obj=bpy.context.object;mat=bpy.data.materials.new('jacket');obj.data.materials.append(mat)
bpy.context.scene.baw_parts.target=obj
assert bpy.ops.baw.parts_analyze()=={'FINISHED'}
assert bpy.ops.baw.parts_add_group(label='自定义 A')=={'FINISHED'}
assert bpy.ops.baw.parts_add_group(label='自定义 B')=={'FINISHED'}
assert bpy.ops.baw.parts_preview()=={'FINISHED'}
preview=bpy.context.scene.baw_parts.preview
colors=[tuple(m.diffuse_color) for m in next(iter(preview.objects)).data.materials]
assert colors[-1]!=colors[-2],'Custom groups must have distinct preview colors'
assert obj.hide_viewport
m.unregister()
assert not obj.hide_viewport,'Disabling the add-on must restore original visibility'
m.register()
out=Path('D:/Agent Workspaces/Agent Temp/BA_Animation_Workflow/testing/parts/installed_report.json')
report={'version':'0.13.0','installed_path':str(base),'enabled':True,'files_match_build':True,'operators_present':True,'actual_installed_analyze_and_preview':True,'unregister_restores_preview':True,'register_cycle':True}
out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');print('PARTS_INSTALLED_OK',report)
