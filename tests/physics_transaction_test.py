"""Real-file transaction regression, parameterized paths and no source writes."""
import bpy, sys, json, hashlib, copy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'extension'))
from ba_animation_workflow import physics as p
from ba_animation_workflow.physics_ui import BakeJob

args = sys.argv[sys.argv.index('--')+1:]
source, out = Path(args[0]), Path(args[1])
out.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(source), load_ui=False, use_scripts=False)
s = bpy.context.scene
r = next(o for o in s.objects if o.type == 'ARMATURE' and o.parent and getattr(o.parent, 'mmd_type', '') == 'ROOT')
original_action = r.animation_data.action
original_signature = p.action_signature(original_action)
original_name = original_action.name
start, end = p.infer_range(s, r)
timeline = (s.render.fps, s.render.fps_base, s.frame_start, s.frame_end, s.use_preview_range,
            s.frame_preview_start, s.frame_preview_end, s.rigidbody_world.point_cache.frame_start,
            s.rigidbody_world.point_cache.frame_end, s.frame_current)
guard = p.fingerprint(s, r)

# Cancel a real worker before it can complete. Parent scene must be unchanged.
job = BakeJob(s, r, start, end, directory=str(out))
job.close()
assert p.fingerprint(s, r) == guard, 'cancel changed input'
assert not job.folder.exists(), 'cancel left snapshot behind'
print('CANCEL_PASS', flush=True)

job = BakeJob(s, r, start, end, directory=str(out))
job.process.wait()
print('WORKER_EXIT', job.process.returncode, job.folder, flush=True)
result = job.finish()
assert p.action_signature(original_action) == original_signature, 'source Action mutated'
assert timeline == (s.render.fps, s.render.fps_base, s.frame_start, s.frame_end, s.use_preview_range,
                    s.frame_preview_start, s.frame_preview_end, s.rigidbody_world.point_cache.frame_start,
                    s.rigidbody_world.point_cache.frame_end, s.frame_current), 'timeline changed'
assert not s.rigidbody_world.enabled
output_action = r.animation_data.action

# All non-physics curves must be bit-for-bit preserved.
prefixes = tuple(r.pose.bones[n].path_from_id()+'.' for n in result['bones'])
base = [c for c in original_signature if not c[0].startswith(prefixes)]
after = [c for c in p.action_signature(output_action) if not c[0].startswith(prefixes)]
assert base == after, 'nonphysical keys changed'

# Order-independent evaluation, including zero, and reload persistence.
frames = [start, -1, 0, 1, 50, 51, 399, 400, 573, 575, end]
def matrices(order):
    data = {}
    for f in order:
        s.frame_set(f)
        ev = r.evaluated_get(bpy.context.evaluated_depsgraph_get())
        data[f] = {n: [list(row) for row in ev.matrix_world@ev.pose.bones[n].matrix] for n in result['bones']}
    return data
before = matrices(frames)
assert before == matrices(list(reversed(frames)))
deliver = out/'physics_baked_regression.blend'
bpy.ops.wm.save_as_mainfile(filepath=str(deliver), copy=True)
bpy.ops.wm.open_mainfile(filepath=str(deliver), load_ui=False, use_scripts=False)
s = bpy.context.scene
r = bpy.data.objects[result['rig']]
assert before == matrices(frames), 'reload changed baked poses'
source_action = r[p.SOURCE]
source_action.name = 'Renamed_Source_Action_For_Restore_Test'
p.restore(s, r)
assert r.animation_data.action == source_action
assert p.action_signature(source_action) == original_signature
assert s.rigidbody_world.enabled
assert p.BACKUP not in r

# Malformed data must fail before any Action or state mutation.
report = p.preflight(s, r, start, end)
count = len(bpy.data.actions)
bad = copy.deepcopy(result)
bad['basis'][0][result['bones'][0]][0][0] = float('nan')
try:
    p.apply_result(s, r, bad, report)
except ValueError:
    pass
else:
    raise AssertionError('non-finite result accepted')
assert len(bpy.data.actions) == count and r.animation_data.action == source_action

# Input edits invalidate a previously finished worker result.
old_guard = p.fingerprint(s, r)
s.render.fps = 30
try:
    p.apply_result(s, r, result, report, old_guard)
except ValueError:
    pass
else:
    raise AssertionError('stale result accepted')
assert r.animation_data.action == source_action
summary = {k:v for k,v in result.items() if k not in {'basis', 'zero_steps'}}
summary.update(cancel_unchanged=True, source_action_unchanged=True, nonphysical_curves_unchanged=True,
               timeline_unchanged=True, random_seek_and_reload=True, restore_after_rename=True,
               invalid_result_rollback=True, stale_input_rejected=True)
(out/'transaction_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf8')
print('PHYSICS_TRANSACTION_PASS', json.dumps(summary, ensure_ascii=False), flush=True)
