"""Portable MMD integration: modes 1/2, frame drivers, moving root, fractional FPS."""
import bpy, sys, json, importlib, math, addon_utils
from pathlib import Path

root_path = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root_path/'extension'))
import ba_animation_workflow as ba
from ba_animation_workflow import physics as p
from ba_animation_workflow.physics_ui import BakeJob

out = Path(sys.argv[sys.argv.index('--')+1])
out.mkdir(parents=True, exist_ok=True)
for addon in tuple(bpy.context.preferences.addons):
    if addon.module.rsplit('.', 1)[-1] == 'ba_animation_workflow':
        addon_utils.disable(addon.module, default_set=False)
ba.register()
assert hasattr(bpy.context.scene.baw_physics, 'rig')
assert hasattr(bpy.ops.baw, 'physics_bake')
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
s = bpy.context.scene
s.render.fps = 30
s.render.fps_base = 1.001
s.frame_start, s.frame_end = 1, 14
s.use_preview_range = True
s.frame_preview_start, s.frame_preview_end = -6, 14
api, module = p.mmd_api()
m = api.Model.create('BA_Physics_Fixture')
r = m.armature()
bpy.context.view_layer.objects.active = r
r.select_set(True)
bpy.ops.object.mode_set(mode='EDIT')
body = r.data.edit_bones.new('body')
body.head, body.tail = (0,0,1.2), (0,0,1.6)
for name, x in [('pendant',-.2), ('hair',.2)]:
    b = r.data.edit_bones.new(name)
    b.head, b.tail = (x,0,1.45), (x,0,1.15)
    b.parent = body
bpy.ops.object.mode_set(mode='OBJECT')
for f, v in [(-6,0), (0,.03), (14,.1)]:
    r.pose.bones['body'].location.x = v
    r.pose.bones['body'].keyframe_insert('location', frame=f)
    m.rootObject().location.x = v
    m.rootObject().rotation_euler.z = v
    m.rootObject().keyframe_insert('location', frame=f)
    m.rootObject().keyframe_insert('rotation_euler', frame=f)
driver = r.pose.bones['body'].driver_add('rotation_euler', 1)
r.pose.bones['body'].rotation_mode = 'XYZ'
driver.driver.expression = 'sin(frame * 0.03) * 0.1'
bodies={}
for name, mode in [('body','0'), ('pendant','1'), ('hair','2')]:
    bpy.ops.mesh.primitive_uv_sphere_add(segments=8, ring_count=4, radius=.06, location=r.data.bones[name].head_local)
    o = bpy.context.object
    o.name = 'Rigid_'+name
    o.parent = m.rigidGroupObject()
    o.mmd_type = 'RIGID_BODY'
    bpy.ops.rigidbody.object_add()
    o.mmd_rigid.type = mode
    o.mmd_rigid.shape = 'SPHERE'
    o.mmd_rigid.size = (.06,0,0)
    o.mmd_rigid.bone = name
    o.rigid_body.mass = .2
    o.rigid_body.linear_damping = .7
    o.rigid_body.angular_damping = .7
    bodies[name]=o
for name in ('pendant','hair'):
    bpy.ops.object.empty_add(location=r.data.bones[name].head_local)
    o=bpy.context.object
    o.name='Joint_'+name
    o.parent=m.jointGroupObject()
    o.mmd_type='JOINT'
    bpy.ops.rigidbody.constraint_add(type='GENERIC_SPRING')
    c=o.rigid_body_constraint
    c.object1,c.object2=bodies['body'],bodies[name]
    for axis in 'xyz':
        setattr(c,'use_limit_lin_'+axis,True)
        setattr(c,'limit_lin_'+axis+'_lower',0)
        setattr(c,'limit_lin_'+axis+'_upper',0)
        setattr(c,'use_limit_ang_'+axis,True)
        setattr(c,'limit_ang_'+axis+'_lower',-.3)
        setattr(c,'limit_ang_'+axis+'_upper',.3)
s.rigidbody_world.enabled=False
s.rigidbody_world.point_cache.frame_start=-6
s.rigidbody_world.point_cache.frame_end=14
s.frame_set(-6)
bpy.context.view_layer.update()
first_body=(r.matrix_world@r.pose.bones['body'].matrix).copy()
s.frame_set(14)
bpy.context.view_layer.update()
last_body=(r.matrix_world@r.pose.bones['body'].matrix).copy()
assert (last_body.translation-first_body.translation).length>.05, 'fixture root did not animate'
assert abs(r.pose.bones['body'].rotation_euler.y-math.sin(14*.03)*.1)<1e-5, 'frame driver did not evaluate'
s.frame_set(-6)
report=p.preflight(s,r,-6,14)
sig=p.action_signature(r.animation_data.action)
# Rejections must happen before mutation, including an ambiguous layout that
# can only be inspected after MMD cleanup in the worker.
try:
    p.preflight(s,r,0,14)
except ValueError:
    pass
else:
    raise AssertionError('missing negative preroll accepted')
constraint=r.pose.bones['hair'].constraints.new('LIMIT_ROTATION')
try:
    p.preflight(s,r,-6,14)
except ValueError:
    pass
else:
    raise AssertionError('double transform constraint accepted')
r.pose.bones['hair'].constraints.remove(constraint)
for o in m.joints():
    o.location.x+=1
bpy.context.view_layer.update()
guard=p.fingerprint(s,r)
failed=BakeJob(s,r,-6,14,directory=str(out))
failed.process.wait()
try:
    failed.finish()
except RuntimeError as exc:
    assert '偏移不一致' in str(exc), str(exc)
    failed.close()
else:
    raise AssertionError('ambiguous offset silently corrected')
assert p.fingerprint(s,r)==guard
for o in m.joints():
    o.location.x-=1
bpy.context.view_layer.update()
job=BakeJob(s,r,-6,14,align=False,directory=str(out))
scene_status=s.baw_physics
scene_status.status='模拟 UI 进度更新'
job.process.wait()
print('SYNTHETIC_WORKER',job.process.returncode,job.folder,flush=True)
result=job.finish()
assert result['basis'][0]!=result['basis'][-1], 'physics fixture produced no local motion'
assert not result['alignment']['applied']
assert not result['alignment']['suspect']
assert result['max_replay_matrix_error']<.0002
assert s.render.fps==30 and abs(s.render.fps_base-1.001)<1e-6
assert s.frame_preview_start==-6
try:
    p.apply_result(s,r,result,report)
except ValueError:
    pass
else:
    raise AssertionError('repeat application accepted')
p.restore(s,r)
assert p.action_signature(r.animation_data.action)==sig
assert not s.rigidbody_world.enabled
ba.unregister()
ba.register()
assert hasattr(bpy.context.scene.baw_physics,'rig')
ba.unregister()
(out/'synthetic_summary.json').write_text(json.dumps({k:v for k,v in result.items() if k not in {'basis'}},ensure_ascii=False,indent=2),encoding='utf8')
print('PHYSICS_SYNTHETIC_PASS',flush=True)
