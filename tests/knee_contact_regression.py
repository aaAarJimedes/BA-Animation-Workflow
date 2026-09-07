"""Regression for knee-plane preservation on the real ninth clip."""
import bpy, importlib, os, json, math
from mathutils import Vector
a=importlib.import_module(os.environ.get('BAW_AUTO_ADDON_MODULE','ba_animation_workflow')+'.auto_director')
c=importlib.import_module(a.__package__+'.foot_contact')
s=bpy.context.scene; cfg=s.baw_auto_director
t=cfg.reuse_target_rig or cfg.target_rig
cfg.reuse_target_rig=t
cfg.remap_prompt_text=bpy.data.texts[os.environ.get('BAW_CONTACT_TEXT','第九段')]
cfg.reuse_foot_contact=True
original=c._solve
metrics={'max_knee_off_axis_degrees':0.,'min_plane_dot':1.,'max_length_error':0.,'max_foot_rotation_error':0.}
def probe(target,names,goal):
    upper,lower,foot=[target.pose.bones[n] for n in names]
    hip,knee,ankle=[b.head.copy() for b in (upper,lower,foot)]
    axis=(ankle-hip).normalized()
    pole=knee-hip-axis*(knee-hip).dot(axis)
    wanted=(target.matrix_world.inverted_safe() @ goal-hip).normalized()
    expected=axis.rotation_difference(wanted) @ pole.normalized()
    before=lower.matrix_basis.to_quaternion()
    foot_q=foot.matrix.to_quaternion()
    lengths=[(knee-hip).length,(ankle-knee).length]
    result=original(target,names,goal)
    delta=before.inverted() @ lower.matrix_basis.to_quaternion()
    offaxis=math.degrees(2*math.asin(min(1.,math.hypot(delta.y,delta.z))))
    solved_axis=(foot.head-upper.head).normalized()
    solved_pole=lower.head-upper.head-solved_axis*(lower.head-upper.head).dot(solved_axis)
    plane_dot=expected.dot(solved_pole.normalized())
    length_error=max(abs(x-y) for x,y in zip(lengths,[(lower.head-upper.head).length,(foot.head-lower.head).length]))
    foot_error=1-abs(foot_q.dot(foot.matrix.to_quaternion()))
    metrics['max_knee_off_axis_degrees']=max(metrics['max_knee_off_axis_degrees'],offaxis)
    metrics['min_plane_dot']=min(metrics['min_plane_dot'],plane_dot)
    metrics['max_length_error']=max(metrics['max_length_error'],length_error)
    metrics['max_foot_rotation_error']=max(metrics['max_foot_rotation_error'],foot_error)
    assert offaxis<2.,('knee twisted',s.frame_current,names,offaxis)
    assert plane_dot>.999,('bend plane changed',s.frame_current,names,plane_dot)
    assert length_error<1e-5
    assert foot_error<1e-5
    return result
c._solve=probe
assert bpy.ops.baw.auto_remap_existing('EXEC_DEFAULT')=={'FINISHED'}
print('KNEE_CONTACT_REGRESSION_PASS',json.dumps(metrics))
