from __future__ import annotations

import json
import importlib
import os
from pathlib import Path

import bpy


if not bpy.app.background:
    raise RuntimeError("Raw retarget renderer refuses to run in Blender UI")
if os.environ.get("BAW_RAW_RETARGET_ALLOW") != "read-only-background-test":
    raise RuntimeError("Set BAW_RAW_RETARGET_ALLOW=read-only-background-test explicitly")

output = Path(os.environ["BAW_RAW_RETARGET_OUTPUT"])
output.mkdir(parents=True, exist_ok=True)
scene = bpy.context.scene
settings = scene.baw_auto_director
target = settings.target_rig
animation_data = target.animation_data
old_bad_action = animation_data.action
boundary = int(round(float(old_bad_action.frame_range[0])))
old_strip = next(
    strip
    for track in animation_data.nla_tracks
    if track.name.startswith("BAW_上一段_")
    for strip in track.strips
    if int(round(float(strip.frame_end))) == boundary
)
old_action = old_strip.action

scene.frame_set(boundary)
animation_data.action = None
animation_data.use_nla = True
bpy.context.view_layer.update()
auto_director = importlib.import_module(
    os.environ.get("BAW_AUTO_ADDON_MODULE", "bl_ext.user_default.ba_animation_workflow")
    + ".auto_director"
)
continuity_json = auto_director._capture_current_pose(target)

result = bpy.ops.ba_motion_bridge.retarget("EXEC_DEFAULT")
if result != {"FINISHED"}:
    raise RuntimeError(f"Raw retarget failed: {result}")
raw_action = target.animation_data.action
if raw_action is None or raw_action == old_bad_action:
    raise RuntimeError("Motion Bridge did not create a fresh raw Action")


def matrix_error(left, right):
    return max(
        abs(float(left[row][column]) - float(right[row][column]))
        for row in range(4)
        for column in range(4)
    )


channels = auto_director._action_bone_channels(raw_action)
animated_names = [name for name in channels if target.pose.bones.get(name) is not None]
root_names = sorted(name for name in animated_names if "location" in channels[name])
root_anchor_names = sorted(
    name
    for name in root_names
    if target.pose.bones[name].parent is None
    or target.pose.bones[name].parent.name not in root_names
)
root_child_names = sorted(set(root_names) - set(root_anchor_names))
body_names = sorted(name for name in animated_names if name not in root_names)
blend_frames = min(
    int(raw_action.frame_range[1]) - boundary,
    max(2, int(round(scene.render.fps * 0.25))),
)
check_frames = sorted({boundary, boundary + blend_frames, boundary + 30, int(raw_action.frame_range[1])})
animation_data.use_nla = False
raw_basis = {}
for frame in check_frames:
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    raw_basis[frame] = {
        name: target.pose.bones[name].matrix_basis.copy() for name in animated_names
    }
animation_data.use_nla = True
captured_rows = {
    row["bone"]: row
    for row in json.loads(continuity_json)
    if isinstance(row, dict) and row.get("bone")
}
unowned_basis_before = {
    bone.name: bone.matrix_basis.copy()
    for bone in target.pose.bones
    if bone.name not in animated_names
}
old_key_count = sum(
    len(curve.keyframe_points)
    for curve in auto_director._iter_action_fcurves(old_action)
)

scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 640
scene.render.resolution_y = 360
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.film_transparent = False
for frame in (boundary, boundary + 1, boundary + 30, int(raw_action.frame_range[1])):
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    scene.render.filepath = str(output / f"raw_retarget_{frame:04d}.png")
    bpy.ops.render.render(write_still=True)

settings.start_behavior = "CURRENT_POSE"
settings.motion_start_frame = boundary
settings.continuity_pose_json = continuity_json
settings.previous_clip_action = old_action
settings.previous_clip_action_name = old_action.name
settings.previous_clip_use_nla = True
auto_director._preserve_previous_clip(settings, raw_action)
auto_director._apply_continuity_pose(scene, settings, raw_action)

if old_key_count != sum(
    len(curve.keyframe_points)
    for curve in auto_director._iter_action_fcurves(old_action)
):
    raise AssertionError("Previous Clip keys changed")
unowned_error = max(
    (matrix_error(target.pose.bones[name].matrix_basis, matrix)
     for name, matrix in unowned_basis_before.items()),
    default=0.0,
)
if unowned_error >= 1e-7:
    raise AssertionError(f"Unowned bone changed: {unowned_error}")

animation_data.use_nla = False
candidate_basis = {}
for frame in check_frames:
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    candidate_basis[frame] = {
        name: target.pose.bones[name].matrix_basis.copy() for name in animated_names
    }
animation_data.use_nla = True

root_delta_error = max(
    (
        matrix_error(
            raw_basis[boundary][name].inverted_safe() @ raw_basis[frame][name],
            candidate_basis[boundary][name].inverted_safe() @ candidate_basis[frame][name],
        )
        for name in root_names
        for frame in check_frames[1:]
    ),
    default=0.0,
)
if root_delta_error >= 2e-4:
    raise AssertionError(f"Root motion delta changed: {root_delta_error}")

body_release_error = max(
    (
        matrix_error(candidate_basis[frame][name], raw_basis[frame][name])
        for name in body_names
        for frame in check_frames
        if frame >= boundary + blend_frames
    ),
    default=0.0,
)
if body_release_error >= 2e-4:
    raise AssertionError(f"Body motion did not return to the raw retarget: {body_release_error}")

captured_body_error = max(
    (
        matrix_error(candidate_basis[boundary][name], auto_director.Matrix(captured_rows[name]["matrix_basis"]))
        for name in body_names
        if name in captured_rows
    ),
    default=0.0,
)
if captured_body_error >= 2e-4:
    raise AssertionError(f"Body does not start from the captured pose: {captured_body_error}")

root_child_start_error = max(
    (
        matrix_error(
            candidate_basis[boundary][name],
            auto_director.Matrix(captured_rows[name]["matrix_basis"]),
        )
        for name in root_child_names
        if name in captured_rows
    ),
    default=0.0,
)
if root_child_start_error >= 2e-4:
    raise AssertionError(
        f"Child root-motion bone double-counted its parent: {root_child_start_error}"
    )
for frame in (boundary - 1, boundary, boundary + 1, boundary + 6, boundary + 30, int(raw_action.frame_range[1])):
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    scene.render.filepath = str(output / f"candidate_{frame:04d}.png")
    bpy.ops.render.render(write_still=True)

print("BAW_RAW_RETARGET=" + json.dumps({
    "status": "PASS",
    "file": bpy.data.filepath,
    "target": target.name,
    "boundary": boundary,
    "raw_action": raw_action.name,
    "frame_range": list(raw_action.frame_range),
    "root_bones": root_names,
    "root_anchors": root_anchor_names,
    "body_bone_count": len(body_names),
    "body_blend_frames": blend_frames,
    "max_root_delta_error": root_delta_error,
    "max_body_release_error": body_release_error,
    "max_captured_body_error": captured_body_error,
    "max_root_child_start_error": root_child_start_error,
    "max_unowned_basis_error": unowned_error,
    "saved": False,
    "cloud_generation_invoked": False,
}, ensure_ascii=False))
