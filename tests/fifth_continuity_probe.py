import bpy, importlib, json, os
a = importlib.import_module(os.environ.get('BAW_AUTO_ADDON_MODULE', 'ba_animation_workflow')+'.auto_director')
s = bpy.context.scene
cfg = s.baw_auto_director
t = cfg.reuse_target_rig or cfg.target_rig
selected = t.animation_data.action
cfg.reuse_target_rig = t
cfg.remap_action = selected
original = a._apply_continuity_pose
def sample(action):
    t.animation_data.action = action
    t.animation_data.use_nla = False
    out = {}
    for f in [342,350,390,420,446]:
        s.frame_set(f); bpy.context.view_layer.update()
        out[f] = {b.name:list(b.matrix_basis.to_euler()) for b in t.pose.bones if b.name in ['センター','グルーブ','上半身','下半身']}
    return out
def probe(scene, settings, action):
    flag = t.animation_data.use_nla
    raw = sample(action)
    t.animation_data.use_nla = flag
    result = original(scene,settings,action)
    post = sample(action)
    t.animation_data.use_nla = flag
    print('FIFTH_COMPARE='+json.dumps({'raw':raw,'post':post}))
    return result
a._apply_continuity_pose = probe
result = bpy.ops.baw.auto_remap_existing('EXEC_DEFAULT',action_name=selected.name)
assert result == {'FINISHED'}, cfg.status_message
print('FIFTH_PROBE_PASS', cfg.status_message)
