"""Repeatable, read-only benchmark. Pass -- baseline or -- optimized."""
import sys, time, json, statistics, cProfile, pstats
from pathlib import Path
import bpy
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'extension'))
from ba_animation_workflow import parts, utils
source = Path('D:/Agent Workspaces/Agent Delivery/Mama_Animation/Character/AvatarBuilder发骨优化/伊落玛丽-AvatarBuilder柔顺发骨.blend')
bpy.ops.wm.open_mainfile(filepath=str(source), load_ui=False, use_scripts=False)
rig = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
objects = parts.sources_for(rig, bpy.context.scene)
results = {}
for name, fn, runs in [('fingerprint', lambda: [parts.fingerprint(o) for o in objects], 5),
                       ('analyze', lambda: parts.analyze(objects), 3),
                       ('dependency_status_1000', lambda: [utils.external_addon_status() for _ in range(1000)], 3)]:
    samples = []
    for _ in range(runs):
        start = time.perf_counter(); fn(); samples.append(time.perf_counter() - start)
    results[name] = {'median_seconds': statistics.median(samples), 'samples': samples}
label = sys.argv[-1] if '--' in sys.argv else 'baseline'
folder = Path('D:/Agent Workspaces/Agent Temp/BA_Animation_Workflow/testing/optimization')
folder.mkdir(parents=True, exist_ok=True)
(folder / (label + '.json')).write_text(json.dumps(results, indent=2), encoding='utf8')
profiler = cProfile.Profile(); profiler.runcall(parts.analyze, objects)
with (folder / (label + '-profile.txt')).open('w', encoding='utf8') as f:
    pstats.Stats(profiler, stream=f).sort_stats('cumulative').print_stats(25)
print('BENCHMARK_OK', json.dumps(results))
