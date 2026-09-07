"""Read-only saved clip boundary position and angular velocity inspection."""
import bpy, importlib, os, json, math
a=importlib.import_module(os.environ.get('BAW_AUTO_ADDON_MODULE','ba_animation_workflow')+'.auto_director')
s=bpy.context.scene; cfg=s.baw_auto_director; t=cfg.reuse_target_rig or cfg.target_rig
ad=t.animation_data
def sample(action,f):
    ad.action=action; ad.use_nla=False; s.frame_set(f); bpy.context.view_layer.update()
    return {b.name:b.matrix_basis.decompose() for b in t.pose.bones if b.name in a._action_bone_channels(action)}
rows=[]
for text in bpy.data.texts:
    if '段' not in text.name: continue
    action=a._resolve_text_action(s,cfg,text,target=t)
    if action is None or a._action_target_name(action)!=t.name: continue
    start,end=a._clip_motion_bounds(action)
    previous=a._find_previous_target_action(t,action,start)
    if previous is None: continue
    p0=sample(previous,start-1); p1=sample(previous,start)
    n0=sample(action,start); n1=sample(action,start+1)
    angular=[]; spatial=[]
    for name in n0.keys() & n1.keys() & p0.keys() & p1.keys():
        v0=p0[name][1].inverted() @ p1[name][1]
        v1=n0[name][1].inverted() @ n1[name][1]
        mismatch=(v0.inverted() @ v1).angle
        mismatch=min(mismatch,2*math.pi-mismatch)
        angular.append((math.degrees(mismatch),name))
        spatial.append(((n1[name][0]-n0[name][0]-(p1[name][0]-p0[name][0])).length,name))
    rows.append(dict(text=text.name,start=start,angular=sorted(angular,reverse=True)[:3],location=sorted(spatial,reverse=True)[:2]))
print('SEAM_PROBE',json.dumps(rows,ensure_ascii=False))
