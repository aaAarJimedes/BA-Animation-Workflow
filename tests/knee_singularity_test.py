"""Near-straight knees must not flip with sub-pixel source noise."""
import bpy, sys, math
from pathlib import Path
from mathutils import Matrix, Quaternion, Vector
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'extension'))
from ba_animation_workflow.foot_contact import _solve
data=bpy.data.armatures.new('KneeSingularity')
rig=bpy.data.objects.new('KneeSingularity',data)
bpy.context.scene.collection.objects.link(rig)
bpy.context.view_layer.objects.active=rig; rig.select_set(True)
bpy.ops.object.mode_set(mode='EDIT')
upper=data.edit_bones.new('upper'); upper.head=(0,0,0); upper.tail=(0,0,-1)
lower=data.edit_bones.new('lower'); lower.head=upper.tail; lower.tail=(0,0,-2); lower.parent=upper
foot=data.edit_bones.new('foot'); foot.head=lower.tail; foot.tail=(0,-.3,-2); foot.parent=lower
bpy.ops.object.mode_set(mode='OBJECT')
prior=None
for epsilon in [-1e-6,0,1e-6,0,-1e-6]:
    for bone in rig.pose.bones:
        bone.rotation_mode='QUATERNION'; bone.matrix_basis=Matrix.Identity(4)
    rig.pose.bones['lower'].rotation_quaternion=Quaternion((1,0,0),epsilon)
    bpy.context.view_layer.update()
    ok,error=_solve(rig,('upper','lower','foot'),Vector((.06,.08,-1.98)))
    assert ok and error<1e-5
    upper,lower,foot=[rig.pose.bones[n] for n in ('upper','lower','foot')]
    axis=(foot.head-upper.head).normalized()
    pole=(lower.head-upper.head-axis*(lower.head-upper.head).dot(axis)).normalized()
    if prior is not None:
        assert pole.dot(prior)>.9999,('straight knee flipped',epsilon)
    prior=pole.copy()
    assert abs((lower.head-upper.head).length-1)<1e-5
    assert abs((foot.head-lower.head).length-1)<1e-5
ok,error=_solve(rig,('upper','lower','foot'),Vector((0,0,-3)))
assert ok and math.isfinite(error) and error>.99
assert (rig.pose.bones['foot'].head-rig.pose.bones['upper'].head).length<2
print('KNEE_SINGULARITY_PASS: stable plane across +/- source noise; unreachable goal does not stretch')
