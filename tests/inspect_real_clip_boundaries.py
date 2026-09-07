from __future__ import annotations

import json
import os

import bpy


if not bpy.app.background:
    raise RuntimeError("Boundary inspection refuses to run in Blender UI")
if os.environ.get("BAW_BOUNDARY_INSPECT_ALLOW") != "read-only-background-test":
    raise RuntimeError("Set BAW_BOUNDARY_INSPECT_ALLOW=read-only-background-test explicitly")


def matrix_rows(matrix):
    return [[float(value) for value in row] for row in matrix]


def vector_values(vector):
    return [float(value) for value in vector]


scene = bpy.context.scene
settings = scene.baw_auto_director
target = settings.target_rig
if target is None or target.type != "ARMATURE":
    raise RuntimeError("Auto Director target rig is missing")
animation_data = target.animation_data
if animation_data is None:
    raise RuntimeError("Target animation data is missing")

action_records = []
actions = []
if animation_data.action is not None:
    actions.append(animation_data.action)
for track in animation_data.nla_tracks:
    for strip in track.strips:
        if strip.action is not None and strip.action not in actions:
            actions.append(strip.action)
for action in actions:
    channels = __import__(
        "bl_ext.user_default.ba_animation_workflow.auto_director",
        fromlist=["_action_bone_channels"],
    )._action_bone_channels(action)
    action_records.append({
        "name": action.name,
        "range": [float(value) for value in action.frame_range],
        "custom_range": [bool(action.use_frame_range), float(action.frame_start), float(action.frame_end)],
        "location_bones": sorted(name for name, paths in channels.items() if "location" in paths),
        "body_blend_frames": action.get("baw_continuity_body_blend_frames"),
        "continuity_root_bones": action.get("baw_continuity_root_bones"),
    })

strip_records = [
    {
        "track": track.name,
        "action": strip.action.name if strip.action else None,
        "frame": [float(strip.frame_start), float(strip.frame_end)],
        "action_frame": [float(strip.action_frame_start), float(strip.action_frame_end)],
        "extrapolation": strip.extrapolation,
        "blend": strip.blend_type,
        "influence": float(strip.influence),
    }
    for track in animation_data.nla_tracks
    for strip in track.strips
]

root_names = sorted({
    name
    for record in action_records
    for name in record["location_bones"]
    if target.pose.bones.get(name) is not None
})
probe_names = root_names + [
    name for name in ("下半身", "上半身", "上半身2", "首", "頭")
    if target.pose.bones.get(name) is not None and name not in root_names
]


def sample_state(frame):
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    evaluated = target.evaluated_get(bpy.context.evaluated_depsgraph_get())
    result = {
        "frame": frame,
        "object_location": vector_values(target.matrix_world.translation),
        "bones": {},
    }
    for name in probe_names:
        bone = target.pose.bones[name]
        evaluated_bone = evaluated.pose.bones.get(name)
        visible = evaluated_bone.matrix if evaluated_bone is not None else bone.matrix
        result["bones"][name] = {
            "basis_location": vector_values(bone.location),
            "basis_matrix": matrix_rows(bone.matrix_basis),
            "visible_location": vector_values(visible.translation),
            "world_location": vector_values(target.matrix_world @ visible.translation),
        }
    return result


combined = [sample_state(frame) for frame in (148, 149, 150, 151, 222, 223, 224, 225)]

# Sample every Action in isolation at its seam so NLA overlap and the authored
# root curves can be distinguished. All state is restored before Blender exits.
active_action = animation_data.action
use_nla = bool(animation_data.use_nla)
isolated = {}
try:
    animation_data.use_nla = False
    for action in actions:
        animation_data.action = action
        isolated[action.name] = [sample_state(frame) for frame in (149, 150, 223, 224)]
finally:
    animation_data.action = active_action
    animation_data.use_nla = use_nla

print("BAW_BOUNDARY_INSPECTION=" + json.dumps({
    "status": "PASS",
    "file": bpy.data.filepath,
    "scene_range": [scene.frame_start, scene.frame_end],
    "active_action": active_action.name if active_action else None,
    "use_nla": use_nla,
    "actions": action_records,
    "strips": strip_records,
    "probe_bones": probe_names,
    "combined": combined,
    "isolated": isolated,
    "saved": False,
    "cloud_generation_invoked": False,
}, ensure_ascii=False))
