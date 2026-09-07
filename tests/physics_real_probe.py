"""Opt-in local regression. Paths are arguments; no character assets in repo."""
import bpy, sys, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'extension'))
from ba_animation_workflow import physics as p

args = sys.argv[sys.argv.index('--')+1:]
source, out = Path(args[0]), Path(args[1])
out.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(source), load_ui=False, use_scripts=False)
s = bpy.context.scene
r = next(o for o in s.objects if o.type == 'ARMATURE' and o.parent and getattr(o.parent, 'mmd_type', '') == 'ROOT')
start, end = p.infer_range(s, r)
report = p.preflight(s, r, start, end)
print('PREFLIGHT', json.dumps(report, ensure_ascii=False), flush=True)
print('FINGERPRINT', p.fingerprint(s, r), flush=True)
job = dict(report, scene=s.name, snapshot=str(source), rig=r.name, align=True,
           progress=str(out/'progress.json'), result=str(out/'result.json'))
(out/'job.json').write_text(json.dumps(job, ensure_ascii=False), encoding='utf8')
from ba_animation_workflow.physics_worker import solve
solve(job, p)
result=json.loads((out/'result.json').read_text(encoding='utf8'))
print('PHYSICS_REAL_PASS', json.dumps({k:v for k,v in result.items() if k not in {'basis','zero_steps'}}, ensure_ascii=False), flush=True)
