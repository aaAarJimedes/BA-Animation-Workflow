import bpy,json,hashlib,tomllib,importlib
from pathlib import Path
module='bl_ext.user_default.ba_animation_workflow'
assert module in bpy.context.preferences.addons,'Installed extension is not enabled'
m=importlib.import_module(module)
base=Path(m.__file__).parent
assert tomllib.loads((base/'blender_manifest.toml').read_text(encoding='utf8'))['version']=='0.12.0'
manifest=json.loads(Path('D:/Agent Workspaces/Agent Delivery/BA_Animation_Workflow/releases/0.12.0/build-manifest.json').read_text())
for name,digest in manifest['source_files'].items():
 assert hashlib.file_digest((base/name).open('rb'),'sha256').hexdigest()==digest,name
assert bpy.ops.baw.inspect_assets.get_rna_type() and bpy.ops.baw.export_render_plan.get_rna_type()
assert bpy.ops.baw.physics_bake.get_rna_type()
m.unregister();m.register()
r={'version':'0.12.0','module':module,'installed_path':str(base),'enabled':True,'files_match_build':True,'unregister_register':True}
Path('D:/Agent Workspaces/Agent Temp/BA_Animation_Workflow/testing/0.12.0/installed_result.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf8')
print('INSTALLED_VERIFIED',r)
