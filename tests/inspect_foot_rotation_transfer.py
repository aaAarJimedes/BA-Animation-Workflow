from __future__ import annotations

import json
import math
import os

import bpy


if not bpy.app.background:
    raise RuntimeError("Foot rotation transfer inspection refuses to run in Blender UI")
if os.environ.get("BAW_FOOT_ROTATION_ALLOW") != "read-only-background-test":
    raise RuntimeError("Set BAW_FOOT_ROTATION_ALLOW=read-only-background-test explicitly")

scene = bpy.context.scene
target = next(
    obj for obj in scene.objects
    if obj.type == "ARMATURE" and obj.animation_data and obj.animation_data.action
    and obj.animation_data.action.get("bam_role") == "RETARGET_OUTPUT"
)
actions = [
    strip.action for track in target.animation_data.nla_tracks for strip in track.strips
    if strip.action is not None
] + [target.animation_data.action]
actions = sorted(
    dict.fromkeys(actions),
    key=lambda action: int(action.get("bam_motion_frame_start", action.frame_range[0])),
)
source = bpy.data.objects.get(str(actions[0].get("bam_source_object", "") or ""))
if source is None:
    source = bpy.data.objects.get("kimodo-soma-rp")

target_before = (target.animation_data.action, bool(target.animation_data.use_nla))
source_before = (source.animation_data.action, bool(source.animation_data.use_nla))


def delta_angle(obj, bone_name):
    pose = obj.pose.bones[bone_name]
    rest = pose.bone.matrix_local.to_quaternion()
    posed = pose.matrix.to_quaternion()
    return math.degrees((posed @ rest.inverted()).angle)


pairs = (
    ("LeftFoot", "足首.L"),
    ("RightFoot", "足首.R"),
    ("LeftToeBase", "つま先.L"),
    ("RightToeBase", "つま先.R"),
)
rows = []
for target_action in actions:
    source_action = bpy.data.actions.get(str(target_action.get("baw_source_action", "") or ""))
    if source_action is None:
        continue
    start = int(target_action.get("bam_motion_frame_start", source_action.frame_range[0]))
    end = int(target_action.get("bam_motion_frame_end", source_action.frame_range[1]))
    for frame in sorted({start, (start + end) // 2, end}):
        source.animation_data.action = source_action
        source.animation_data.use_nla = False
        target.animation_data.action = target_action
        target.animation_data.use_nla = False
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        values = []
        for source_bone, target_bone in pairs:
            if source_bone not in source.pose.bones or target_bone not in target.pose.bones:
                continue
            values.append({
                "source_bone": source_bone,
                "target_bone": target_bone,
                "source_delta_degrees": delta_angle(source, source_bone),
                "target_delta_degrees": delta_angle(target, target_bone),
                "source_basis_scale": list(source.pose.bones[source_bone].matrix_basis.to_scale()),
                "target_basis_scale": list(target.pose.bones[target_bone].matrix_basis.to_scale()),
            })
        rows.append({
            "target_action": target_action.name,
            "source_action": source_action.name,
            "frame": frame,
            "pairs": values,
        })

target.animation_data.action, target.animation_data.use_nla = target_before
source.animation_data.action, source.animation_data.use_nla = source_before
print("BAW_FOOT_ROTATION_TRANSFER=" + json.dumps({
    "file": bpy.data.filepath,
    "target": target.name,
    "source": source.name,
    "rows": rows,
    "saved": False,
    "cloud_generation_invoked": False,
}, ensure_ascii=False))
