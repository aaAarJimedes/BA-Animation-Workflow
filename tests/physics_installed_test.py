"""Verify an installed build and optionally write a separate review project."""
import bpy, sys, json, importlib, hashlib, tomllib
from pathlib import Path

source, output, build_manifest, report_path = map(Path, sys.argv[sys.argv.index('--')+1:])
if output.exists():
    raise RuntimeError('Refusing to replace an existing review file: '+str(output))
source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
module=importlib.import_module('bl_ext.user_default.ba_animation_workflow')
installed=Path(module.__file__).parent
manifest=json.loads(build_manifest.read_text(encoding='utf8'))
assert tomllib.loads((installed/'blender_manifest.toml').read_text(encoding='utf8'))['version']==manifest['version']
for name, digest in manifest['source_files'].items():
    assert hashlib.sha256((installed/name).read_bytes()).hexdigest()==digest, name
for name in ('physics_use_range','physics_check','physics_bake','physics_restore'):
    assert getattr(bpy.ops.baw,name).get_rna_type()
bpy.ops.wm.open_mainfile(filepath=str(source),load_ui=False,use_scripts=False)
s=bpy.context.scene
r=next(o for o in s.objects if o.type=='ARMATURE' and o.parent and getattr(o.parent,'mmd_type','')=='ROOT')
start,end=module.physics.infer_range(s,r)
s.baw_physics.rig=r
s.baw_physics.start,s.baw_physics.end=start,end
original=r.animation_data.action
signature=module.physics.action_signature(original)
job=module.physics_ui.BakeJob(s,r,start,end,directory=str(report_path.parent))
job.process.wait()
print('INSTALLED_WORKER',job.process.returncode,job.folder,flush=True)
result=job.finish()
assert module.physics.action_signature(original)==signature
s.frame_set(0)
bpy.ops.wm.save_as_mainfile(filepath=str(output),copy=True)
assert hashlib.sha256(source.read_bytes()).hexdigest()==source_hash
data={k:v for k,v in result.items() if k!='basis'}
data.update(installed_module=str(installed),version=manifest['version'],source_sha256=source_hash,
            review_file=str(output),package_sha256=manifest['sha256'])
report_path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
print('PHYSICS_INSTALLED_PASS',flush=True)
