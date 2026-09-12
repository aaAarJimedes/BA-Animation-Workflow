"""Blender integration checks: batching, saved source binding, physics gate."""
import bpy,sys,json,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'extension'))
import ba_animation_workflow as ba
from ba_animation_workflow import render_plan as p
ba.register()
assert p.frame_batches(0,778,48)[-1]=={'start':768,'end':778,'frames':11}
assert sum(x['frames'] for x in p.frame_batches(-30,778,48))==809
for args in [(3,2,48),(0,10,0),(0,10,1.5)]:
 try:p.frame_batches(*args)
 except ValueError:pass
 else:raise AssertionError('invalid range accepted')
out=Path(sys.argv[sys.argv.index('--')+1]);out.mkdir(parents=True,exist_ok=True)
s=bpy.context.scene
s.render.fps=24;s.render.fps_base=1.001;s.frame_start=-30;s.frame_end=778
timeline=(s.frame_start,s.frame_end,s.render.fps)
bpy.context.object.keyframe_insert(data_path='location',frame=-30)
bpy.context.object.keyframe_insert(data_path='location',frame=0)
negative_action=bpy.context.object.animation_data.action
bpy.context.preferences.filepaths.save_version=0
source=out/'plan_source.blend'
bpy.ops.wm.save_as_mainfile(filepath=str(source),check_existing=False)
plan=p.create_plan(s,0,778,48)
assert plan['frame_count']==779 and plan['scene_timeline']==list(timeline[:2])
assert plan['effective_fps']==24/s.render.fps_base
assert (s.frame_start,s.frame_end,s.render.fps)==timeline
assert negative_action.curve_frame_range[0]==-30
p.check_source(plan)
plan['source_sha256']='0'*64
try:p.check_source(plan)
except ValueError:pass
else:raise AssertionError('source drift accepted')
bad=bpy.data.images.new('missing_external',1,1)
bad.source='FILE';bad.filepath=str(out/'not_here.png')
bpy.ops.wm.save_as_mainfile(filepath=str(source),check_existing=False)
try:p.create_plan(s,0,778,48)
except ValueError:pass
else:raise AssertionError('external dependency accepted')
bpy.data.images.remove(bad)
s.frame_step=2
try:p.create_plan(s,0,778,48)
except ValueError:pass
else:raise AssertionError('frame step accepted')
s.frame_step=1
bpy.ops.rigidbody.world_add()
bpy.ops.wm.save_as_mainfile(filepath=str(source),check_existing=False)
try:p.create_plan(s,0,778,48)
except ValueError:pass
else:raise AssertionError('live physics accepted')
ba.unregister();ba.register();ba.unregister()
print('RENDER_PLAN_TEST_PASS')
