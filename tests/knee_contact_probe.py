import bpy, importlib, os, json, math
a=importlib.import_module(os.environ.get('BAW_AUTO_ADDON_MODULE','ba_animation_workflow')+'.auto_director')
c=importlib.import_module(a.__package__+'.foot_contact')
s=bpy.context.scene; cfg=s.baw_auto_director
t=cfg.reuse_target_rig or cfg.target_rig
cfg.reuse_target_rig=t
cfg.remap_prompt_text=bpy.data.texts[os.environ.get('BAW_CONTACT_TEXT','第八段')]
cfg.reuse_foot_contact=True
original=c._solve
print('KNEE_GEOMETRY',[(side,(t.pose.bones['足'+side].tail-t.pose.bones['ひざ'+side].head).length,(t.pose.bones['ひざ'+side].tail-t.pose.bones['足首'+side].head).length) for side in ('.L','.R')])
rows=[]
def probe(target,names,goal,*args,**kwargs):
    upper,lower,foot=[target.pose.bones[n] for n in names]
    pre=lower.matrix_basis.to_quaternion()
    hip,knee,ankle=[b.head.copy() for b in (upper,lower,foot)]
    axis=(ankle-hip).normalized()
    pole=knee-hip-axis*(knee-hip).dot(axis)
    result=original(target,names,goal,*args,**kwargs)
    post=lower.matrix_basis.to_quaternion()
    delta=pre.inverted() @ post
    swing=(delta.y*delta.y+delta.z*delta.z)**.5
    rows.append(dict(f=s.frame_current,bone=names[1],pole=pole.length,swing=swing,before=list(pre.to_euler()),after=list(post.to_euler())))
    return result
c._solve=probe
assert bpy.ops.baw.auto_remap_existing('EXEC_DEFAULT')=={'FINISHED'}
print('KNEE_PROBE',json.dumps(sorted(rows,key=lambda r:-r['swing'])[:8],ensure_ascii=False))
