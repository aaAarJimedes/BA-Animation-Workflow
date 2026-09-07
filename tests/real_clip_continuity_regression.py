from __future__ import annotations

import importlib
import json
import os

import bpy


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def matrix_error(left, right) -> float:
    return max(
        abs(float(left[row][column]) - float(right[row][column]))
        for row in range(4)
        for column in range(4)
    )


check(bpy.app.background, "Real continuity regression refuses to run in Blender UI")
check(
    os.environ.get("BAW_REAL_CONTINUITY_ALLOW") == "read-only-background-test",
    "Set BAW_REAL_CONTINUITY_ALLOW=read-only-background-test explicitly",
)
check(bool(bpy.data.filepath), "Open a real .blend before running the regression")

module_name = os.environ.get(
    "BAW_AUTO_ADDON_MODULE",
    "bl_ext.user_default.ba_animation_workflow",
)
auto_director = importlib.import_module(module_name + ".auto_director")
scene = bpy.context.scene
settings = scene.baw_auto_director
target = settings.target_rig
check(target is not None and target.type == "ARMATURE", "Auto Director target rig is missing")
animation_data = target.animation_data
check(animation_data is not None and animation_data.action is not None, "Active generated Clip is missing")

new_action = animation_data.action
boundary = int(round(float(new_action.frame_range[0])))
check(boundary > scene.frame_start, "The file does not contain a later Clip")
old_strip = next(
    (
        strip
        for track in animation_data.nla_tracks
        if track.name.startswith("BAW_上一段_")
        for strip in track.strips
        if int(round(float(strip.frame_end))) == boundary
    ),
    None,
)
check(old_strip is not None and old_strip.action is not None, "Previous BA continuity strip is missing")
old_action = old_strip.action
object_matrix_before = target.matrix_world.copy()

channels = auto_director._action_bone_channels(new_action)
animated_names = [name for name in channels if target.pose.bones.get(name) is not None]
check(bool(animated_names), "The later Clip has no target pose-bone channels")
root_names = [name for name in animated_names if "location" in channels[name]]
body_names = [name for name in animated_names if name not in root_names]
blend_frames = min(
    int(new_action.frame_range[1]) - boundary,
    max(2, int(round(scene.render.fps * 0.25))),
)
old_channels = auto_director._action_bone_channels(old_action)
old_animated_names = [
    name for name in old_channels if target.pose.bones.get(name) is not None
]
check(bool(old_animated_names), "The previous Clip has no target pose-bone channels")

# Capture the unmodified generated motion delta without letting the old NLA
# participate. This is the post-Accept/retarget result that must be preserved.
animation_data.use_nla = False
animation_data.action = new_action
generated = {}
for frame in (boundary, boundary + 1, boundary + blend_frames, int(new_action.frame_range[1])):
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    generated[frame] = {
        name: target.pose.bones[name].matrix_basis.copy() for name in animated_names
    }

# Reconstruct the actual handoff pose from the previous Clip only. Nothing is
# saved: Blender exits after the in-memory regression.
animation_data.action = None
animation_data.use_nla = True
previous_visible = {}
for frame in (boundary - 1, boundary):
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    previous_visible[frame] = {
        bone.name: bone.matrix.copy() for bone in target.pose.bones
    }
continuity_json = auto_director._capture_current_pose(target)
continuity_rows = {
    row["bone"]: row
    for row in json.loads(continuity_json)
    if isinstance(row, dict) and row.get("bone")
}

settings.start_behavior = "CURRENT_POSE"
settings.motion_start_frame = boundary
settings.continuity_pose_json = continuity_json
settings.previous_clip_action = old_action
settings.previous_clip_action_name = old_action.name
settings.previous_clip_use_nla = True
animation_data.action = new_action
animation_data.use_nla = True
scene.frame_set(boundary)
bpy.context.view_layer.update()
unowned_basis_before = {
    bone.name: bone.matrix_basis.copy()
    for bone in target.pose.bones
    if bone.name not in animated_names
}

check(auto_director._preserve_previous_clip(settings, new_action) == 0, "Existing NLA was duplicated")
rebased_bones = auto_director._apply_continuity_pose(scene, settings, new_action)
check(rebased_bones == len(animated_names), "Not every generated bone was rebased")
unowned_basis_error = max(
    matrix_error(target.pose.bones[name].matrix_basis, matrix)
    for name, matrix in unowned_basis_before.items()
)
check(unowned_basis_error < 1e-7, f"Rebase mutated an unowned MMD control bone: {unowned_basis_error}")
check(old_strip.extrapolation == "NOTHING", "Legacy previous Clip still holds after its boundary")
check(new_action.use_frame_range and int(new_action.frame_start) == boundary, "New Clip starts before its boundary")
check(matrix_error(target.matrix_world, object_matrix_before) < 1e-7, "Target object placement changed")

# The handoff frame must equal the old visible pose, while the previous frame
# must remain identical to the original first Clip.
for frame in (boundary - 1, boundary):
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    # Only compare channels authored by the relevant Action. Unkeyed MMD D
    # bones depend on interactive depsgraph/constraint evaluation and can stay
    # stale in background mode even when neither Action changed them.
    names = old_animated_names if frame == boundary - 1 else animated_names
    errors = sorted(
        (
            matrix_error(target.pose.bones[name].matrix, previous_visible[frame][name]),
            name,
        )
        for name in names
    )
    error = errors[-1][0]
    if error >= 2e-4:
        active = animation_data.action
        animation_data.action = None
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        old_only_errors = sorted(
            (
                matrix_error(target.pose.bones[name].matrix, previous_visible[frame][name]),
                name,
            )
            for name in names
        )
        animation_data.action = active
        print("BAW_REAL_CLIP_DIAGNOSTIC=" + json.dumps({
            "frame": frame,
            "active_top_errors": errors[-8:],
            "old_only_top_errors": old_only_errors[-8:],
            "action_extrapolation": animation_data.action_extrapolation,
            "action_custom_range": [new_action.use_frame_range, new_action.frame_start, new_action.frame_end],
            "strip": [old_strip.frame_start, old_strip.frame_end, old_strip.action_frame_start, old_strip.action_frame_end, old_strip.extrapolation],
        }, ensure_ascii=False))
    check(error < 2e-4, f"Visible continuity changed at frame {frame}: {error}")

# Root motion must retain the raw relative displacement/facing through the full
# Clip. Body bones intentionally blend only at the handoff, then must become
# byte-for-byte equivalent to the raw generated motion again.
animation_data.use_nla = False
rebased = {}
for frame in (boundary, boundary + 1, boundary + blend_frames, int(new_action.frame_range[1])):
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    rebased[frame] = {
        name: target.pose.bones[name].matrix_basis.copy() for name in animated_names
    }
root_delta_error = max(
    (
        matrix_error(
            generated[boundary][name].inverted_safe() @ generated[boundary + 1][name],
            rebased[boundary][name].inverted_safe() @ rebased[boundary + 1][name],
        )
        for name in root_names
    ),
    default=0.0,
)
check(root_delta_error < 2e-4, f"Root motion delta changed during rebase: {root_delta_error}")
body_release_error = max(
    (
        matrix_error(rebased[frame][name], generated[frame][name])
        for name in body_names
        for frame in (boundary + blend_frames, int(new_action.frame_range[1]))
    ),
    default=0.0,
)
check(body_release_error < 2e-4, f"Body motion did not return to raw generation: {body_release_error}")
captured_body_error = max(
    (
        matrix_error(
            rebased[boundary][name],
            auto_director.Matrix(continuity_rows[name]["matrix_basis"]),
        )
        for name in body_names
        if name in continuity_rows
    ),
    default=0.0,
)
check(captured_body_error < 2e-4, f"Body does not begin from the captured pose: {captured_body_error}")

payload = {
    "status": "PASS",
    "file": bpy.data.filepath,
    "target": target.name,
    "boundary": boundary,
    "previous_action": old_action.name,
    "new_action": new_action.name,
    "rebased_bones": rebased_bones,
    "root_bones": root_names,
    "body_bone_count": len(body_names),
    "body_blend_frames": blend_frames,
    "object_world_unchanged": True,
    "old_strip_extrapolation": old_strip.extrapolation,
    "max_unowned_basis_error": unowned_basis_error,
    "max_root_delta_error": root_delta_error,
    "max_body_release_error": body_release_error,
    "max_captured_body_error": captured_body_error,
    "saved": False,
    "cloud_generation_invoked": False,
}
print("BAW_REAL_CLIP_CONTINUITY=" + json.dumps(payload, ensure_ascii=False))
