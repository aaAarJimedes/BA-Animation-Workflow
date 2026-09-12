import bpy,sys,math,json,importlib.util
from pathlib import Path
from mathutils import Matrix,Vector
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'BA_Animation_Workflow/extension'),str(ROOT/'Motion_Bridge/Proscenium-Motion-Bridge')]
import ba_animation_workflow as ba
import proscenium_motion_bridge as pmb
ba.register();pmb.register()
from ba_animation_workflow.finishing import bake_prop_contact,restore_prop_contact,inspect_motion
from proscenium_motion_bridge.action_access import _bind_action
s=bpy.context.scene
bpy.ops.object.armature_add();rig=bpy.context.object;bone=rig.pose.bones[0];bone.name='RightHand'
for f,loc in [(1,(0,0,0)),(10,(1,2,.5))]:
    bone.location=loc;bone.keyframe_insert('location',frame=f)
prop=bpy.data.objects.new('TestProp',None);s.collection.objects.link(prop);prop.location=(.2,.1,.4)
original=prop.matrix_world.copy();s.frame_set(1);bpy.context.view_layer.update();original=prop.matrix_world.copy()
grip=(rig.matrix_world@bone.matrix).copy();offset=grip.inverted()@original
s.frame_set(4,subframe=.25)
action=bake_prop_contact(s,rig,prop,'RightHand',1,10)
assert s.frame_current==4 and abs(s.frame_subframe-.25)<1e-6
errors=[]
for f in [1,5,10,15]:
    s.frame_set(f);bpy.context.view_layer.update()
    actual=prop.evaluated_get(bpy.context.evaluated_depsgraph_get()).matrix_world
    expected=rig.matrix_world@rig.pose.bones['RightHand'].matrix@offset
    errors.append((actual.translation-expected.translation).length)
assert max(errors)<1e-5,errors
try:bake_prop_contact(s,rig,prop,'RightHand',1,10)
except ValueError:pass
else:raise AssertionError('Must protect existing animated prop')
restore_prop_contact(prop);bpy.context.view_layer.update()
assert (prop.matrix_world.translation-original.translation).length<1e-6
empty=bpy.data.actions.new('SingleSlot');slot=empty.slots.new('OBJECT',rig.name)
_bind_action(rig.animation_data,empty);assert rig.animation_data.action_slot==slot
multi=bpy.data.actions.new('Ambiguous');multi.slots.new('OBJECT','AnotherA');multi.slots.new('OBJECT','AnotherB')
try:_bind_action(rig.animation_data,multi)
except RuntimeError:pass
else:raise AssertionError('Ambiguous slots must not silently select')
assert rig.animation_data.action==empty
settings=s.baw_auto_director
settings.creative_prompt='A person turns their head to the right.'
s.render.fps=30;s.render.fps_base=1.001
plan=ba.auto_director.compile_plan(settings)
assert abs(plan['fps']-s.render.fps/s.render.fps_base)<1e-8
assert s.render.fps==30 and abs(s.render.fps_base-1.001)<1e-6
report={'prop_max_error':max(errors),'slot_ambiguity_rollback':True,'fractional_fps_preserved':True}

pmb.unregister();ba.unregister()
print('NEW_FEATURE_TESTS_PASS',json.dumps(report))
