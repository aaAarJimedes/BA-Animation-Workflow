"""Read-only real-project regression: no save, no generation request."""
import bpy, importlib, os, json, math
from mathutils import Vector, Matrix
a = importlib.import_module(os.environ.get('BAW_AUTO_ADDON_MODULE', 'ba_animation_workflow')+'.auto_director')
s = bpy.context.scene
cfg = s.baw_auto_director
t = cfg.reuse_target_rig or cfg.target_rig
cfg.reuse_target_rig = t
def poses():
    out = {}
    for frame in [100,175,260,315,370,420]:
        s.frame_set(frame); bpy.context.view_layer.update()
        out[frame] = {b.name:b.matrix.copy() for b in t.pose.bones}
    return out
before = poses()
fifth = t.animation_data.action
existing = {x.name:[(c.data_path,c.array_index,[(tuple(k.co),k.interpolation) for k in c.keyframe_points]) for c in a._iter_action_fcurves(x)] for x in bpy.data.actions if a._is_retarget_output_action(x) and a._clip_motion_bounds(x)[1] <= 342}
for name in ['第三段', '第五段', '第三段', '第五段']:
    cfg.remap_prompt_text = bpy.data.texts[name]
    selected = cfg.remap_action
    assert selected is not None, name
    assert t.animation_data.action == selected, name
    start,end = a._clip_motion_bounds(selected)
    assert s.frame_current == start
    if hasattr(s, 'proscenium'):
        block = s.proscenium.prompt_blocks[s.proscenium.active_block_index]
        assert block.prompt == cfg.remap_prompt_text.as_string()
        assert (block.frame_start,block.frame_end)==(start,end)
    after = poses()
    error = max(abs(before[f][b][i][j]-after[f][b][i][j]) for f in before for b in before[f] for i in range(4) for j in range(4))
    assert error < 1e-4, ('selection changed animation', name, error)
assert cfg.remap_action == fifth
text = bpy.data.texts['第五段']
content = text.as_string()
text.clear(); text.write('Edited prompt: keep this accepted take for local reuse.')
assert a._resolve_text_action(s,cfg,text,target=t) == fifth, 'Editing text broke stable association'
text.clear(); text.write(content)
duplicate = text.copy()
assert not a._action_matches_text(fifth,duplicate), 'Copied text silently took ownership'
assert a._ensure_text_clip_id(duplicate) != text['baw_clip_id']
bpy.data.texts.remove(duplicate)
original = a._apply_continuity_pose
metrics = {}
def corrected(scene, settings, action):
    flag = t.animation_data.use_nla
    t.animation_data.action = action
    t.animation_data.use_nla = False
    raw = {}
    for frame in range(342,447):
        s.frame_set(frame); bpy.context.view_layer.update()
        raw[frame] = {b.name:b.matrix_basis.copy() for b in t.pose.bones if b.name in ['センター','グルーブ']}
    t.animation_data.use_nla = flag
    result = original(scene,settings,action)
    rows = {row['bone']:row for row in json.loads(settings.continuity_pose_json)}
    t.animation_data.use_nla = False
    s.frame_set(342); bpy.context.view_layer.update()
    seam = max(abs(t.pose.bones[name].matrix_basis[i][j]-rows[name]['matrix_basis'][i][j]) for name in raw[342] for i in range(4) for j in range(4))
    assert seam < 1e-4, ('seam',seam)
    max_tilt = 0
    for frame in range(349,447):
        s.frame_set(frame); bpy.context.view_layer.update()
        for name in raw[frame]:
            b = t.pose.bones[name]
            delta = b.matrix_basis.to_quaternion() @ raw[frame][name].to_quaternion().inverted()
            rest = b.bone.matrix_local
            if b.parent:
                rest = b.parent.matrix @ b.parent.bone.matrix_local.inverted_safe() @ rest
            up = ((t.matrix_world @ rest).to_3x3().inverted_safe() @ Vector((0,0,1))).normalized()
            max_tilt = max(max_tilt,(delta @ up - up).length)
    assert max_tilt < 1e-4, ('persistent tilt',max_tilt)
    t.animation_data.use_nla = flag
    metrics.update(seam_matrix_error=seam,persistent_tilt_vector_error=max_tilt)
    return result
a._apply_continuity_pose = corrected
assert bpy.ops.baw.auto_remap_existing('EXEC_DEFAULT',action_name=fifth.name) == {'FINISHED'}
for name,keys in existing.items():
    action = bpy.data.actions.get(name)
    assert action is not None, ('old action deleted',name)
    assert keys == [(c.data_path,c.array_index,[(tuple(k.co),k.interpolation) for k in c.keyframe_points]) for c in a._iter_action_fcurves(action)], ('old keys changed',name)
after = poses()
for f in [100,175,260,315]:
    error = max(abs(before[f][b][i][j]-after[f][b][i][j]) for b in before[f] for i in range(4) for j in range(4))
    assert error < 1e-4, ('remap changed old clip',f,error)
print('FIFTH_REUSE_REGRESSION='+json.dumps(dict(status='PASS',saved=False,cloud_generation=False,timeline_test=hasattr(s,'proscenium'),**metrics)))
