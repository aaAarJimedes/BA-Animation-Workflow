from __future__ import annotations

import json

import bpy


scene = bpy.context.scene
settings = getattr(scene, "baw_auto_director", None)
target = getattr(settings, "target_rig", None) if settings is not None else None

if target is None:
    target = next(
        (obj for obj in bpy.context.selected_objects if obj.type == "ARMATURE"),
        None,
    )

payload = {
    "file": bpy.data.filepath,
    "frame": scene.frame_current,
    "target": getattr(target, "name", None),
    "object_matrix_world": [list(row) for row in target.matrix_world] if target else None,
    "active_action": None,
    "nla": [],
    "samples": [],
}

if target is not None and target.animation_data is not None:
    animation_data = target.animation_data
    action = animation_data.action
    if action is not None:
        payload["active_action"] = {
            "name": action.name,
            "frame_range": list(action.frame_range),
            "custom_range": [action.frame_start, action.frame_end]
            if action.use_frame_range
            else None,
            "properties": {
                key: action[key]
                for key in action.keys()
                if str(key).startswith("bam_")
            },
        }
    boundaries = {scene.frame_current}
    for track in animation_data.nla_tracks:
        row = {"name": track.name, "mute": track.mute, "strips": []}
        for strip in track.strips:
            boundaries.update((int(strip.frame_start), int(strip.frame_end)))
            row["strips"].append({
                "name": strip.name,
                "action": getattr(strip.action, "name", None),
                "frame": [strip.frame_start, strip.frame_end],
                "action_frame": [strip.action_frame_start, strip.action_frame_end],
                "blend": strip.blend_type,
                "extrapolation": strip.extrapolation,
                "influence": strip.influence,
            })
        payload["nla"].append(row)

    likely_roots = {
        "全ての親", "全親", "センター", "グルーブ", "center", "groove",
        "root", "Root", "c_pos", "c_traj", "c_root_master.x",
    }
    bone_names = [bone.name for bone in target.pose.bones if bone.name in likely_roots]
    for frame in sorted(boundaries | {value - 1 for value in boundaries} | {value + 1 for value in boundaries}):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        payload["samples"].append({
            "frame": frame,
            "bones": {
                name: {
                    "location": list(target.pose.bones[name].location),
                    "rotation": list(target.pose.bones[name].matrix.to_quaternion()),
                    "matrix_translation": list(target.pose.bones[name].matrix.translation),
                }
                for name in bone_names
            },
        })

print("BAW_CLIP_CONTINUITY=" + json.dumps(payload, ensure_ascii=False, default=str))
