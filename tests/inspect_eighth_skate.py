"""Inspect saved eighth clip and a disposable raw remap; never save."""
import bpy, importlib, os, json
a=importlib.import_module(os.environ.get('BAW_AUTO_ADDON_MODULE','ba_animation_workflow')+'.auto_director')
s=bpy.context.scene; cfg=s.baw_auto_director
t=cfg.reuse_target_rig or cfg.target_rig
text=bpy.data.texts.get('第八段')
print('EIGHTH_TEXTS',[(x.name,x.as_string()[:120]) for x in bpy.data.texts if '段' in x.name])
assert text is not None,'Saved project has no eighth text'
act=a._resolve_text_action(s,cfg,text,target=t,persist=False)
assert act is not None,'No associated eighth action'
src=a._find_linked_source_action(act)
rig=bpy.data.objects.get(act.get('bam_source_object','')) or s.ba_motion_bridge_settings.source_rig
lo,hi=a._clip_motion_bounds(act)
print('EIGHTH_META',json.dumps(dict(target=t.name,action=act.name,source=src.name,source_rig=rig.name,start=lo,end=hi,metadata=dict(act.items())),ensure_ascii=False,default=str))
print('EIGHTH_BONES',[(b.name,b.parent.name if b.parent else None,[(c.name,c.type,c.mute,c.influence) for c in b.constraints]) for b in t.pose.bones if any(k in b.name for k in ['足','ひざ','センター','グルーブ'])])
def sample(obj,names):
    rows=[]
    for f in range(lo,hi+1):
        s.frame_set(f); bpy.context.view_layer.update()
        ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        rows.append({name:list(ev.matrix_world @ ev.pose.bones[name].head) for name in names if name in ev.pose.bones})
    return rows
def metrics(rows):
    out={}
    for n in rows[0]:
        from mathutils import Vector
        pts=[Vector(r[n]) for r in rows]
        out[n]={'span_xyz':[max(p[i] for p in pts)-min(p[i] for p in pts) for i in range(3)],'max_step':max((x-y).length for x,y in zip(pts,pts[1:])),'first':list(pts[0]),'last':list(pts[-1])}
    return out
names=['足首.L','足首.R','足首D.L','足首D.R','足先EX.L','足先EX.R','センター','グルーブ']
saved=sample(t,names)
rig.animation_data.action=src; rig.animation_data.use_nla=False
reference=sample(rig,['Hips','LeftFoot','RightFoot','LeftToeBase','RightToeBase'])
print('EIGHTH_SAVED',json.dumps(metrics(saved),ensure_ascii=False))
print('EIGHTH_REFERENCE',json.dumps(metrics(reference),ensure_ascii=False))
cfg.remap_action=act
original=a._apply_continuity_pose
def probe(scene,settings,action):
    t.animation_data.action=action
    flag=t.animation_data.use_nla; t.animation_data.use_nla=False
    print('EIGHTH_RAW',json.dumps(metrics(sample(t,names)),ensure_ascii=False))
    raw_centers={}
    raw_rotations={}
    for f in range(lo,hi+1):
        s.frame_set(f); bpy.context.view_layer.update()
        raw_centers[f]=(t.matrix_world @ t.pose.bones['センター'].matrix).translation.copy()
        raw_rotations[f]=(t.matrix_world @ t.pose.bones['グルーブ'].matrix).to_quaternion()
    t.animation_data.use_nla=flag
    result=original(scene,settings,action)
    print('EIGHTH_POST',json.dumps(metrics(sample(t,names)),ensure_ascii=False))
    s.frame_set(lo+10); bpy.context.view_layer.update()
    q=(t.matrix_world @ t.pose.bones['グルーブ'].matrix).to_quaternion() @ raw_rotations[lo+10].inverted()
    # Diagnostic only: rotate the Center displacement by the same world yaw
    # used for the Groove's orientation. Do not save the test action.
    for f in range(lo,hi+1):
        s.frame_set(f); bpy.context.view_layer.update()
        bone=t.pose.bones['センター']
        d=raw_centers[f]-raw_centers[lo]
        m=bone.matrix.copy()
        m.translation += t.matrix_world.to_3x3().inverted() @ (q @ d-d)
        bone.matrix=m
        bone.keyframe_insert('location',frame=f)
    print('EIGHTH_UNIFIED_ROOT_TEST',json.dumps(metrics(sample(t,names)[7:]),ensure_ascii=False))
    print('EIGHTH_ALIGNMENT_DEGREES',q.angle*180/3.141592653589793)
    return result
a._apply_continuity_pose=probe
assert bpy.ops.baw.auto_remap_existing('EXEC_DEFAULT',action_name=act.name)=={'FINISHED'}
print('EIGHTH_INSPECTION_COMPLETE_NO_SAVE')
