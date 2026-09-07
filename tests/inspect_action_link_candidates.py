from __future__ import annotations

import json
import os

import bpy


if not bpy.app.background:
    raise RuntimeError("Action-link inspection refuses to run in Blender UI")
if os.environ.get("BAW_ACTION_LINK_INSPECT_ALLOW") != "read-only-background-test":
    raise RuntimeError("Set BAW_ACTION_LINK_INSPECT_ALLOW=read-only-background-test explicitly")

scene = bpy.context.scene
settings = scene.baw_auto_director
target = settings.target_rig
bridge = scene.ba_motion_bridge_settings
source = bridge.source_rig


def action_info(action):
    return {
        "name": action.name,
        "range": [float(value) for value in action.frame_range],
        "props": {key: action[key] for key in action.keys() if key != "_RNA_UI"},
    }


def animation_info(obj):
    animation_data = getattr(obj, "animation_data", None)
    if animation_data is None:
        return None
    return {
        "active": action_info(animation_data.action) if animation_data.action else None,
        "use_nla": bool(animation_data.use_nla),
        "strips": [
            {
                "track": track.name,
                "mute": bool(track.mute),
                "strip": strip.name,
                "strip_mute": bool(strip.mute),
                "frame": [float(strip.frame_start), float(strip.frame_end)],
                "action": action_info(strip.action) if strip.action else None,
            }
            for track in animation_data.nla_tracks
            for strip in track.strips
        ],
    }


print("BAW_ACTION_LINK_CANDIDATES=" + json.dumps({
    "file": bpy.data.filepath,
    "target": target.name if target else None,
    "source": source.name if source else None,
    "target_animation": animation_info(target),
    "source_animation": animation_info(source),
    "all_proscenium_actions": [
        action_info(action)
        for action in bpy.data.actions
        if action.name.startswith("Proscenium_Motion:")
    ],
    "texts": [
        {
            "name": text.name,
            "fake_user": bool(text.use_fake_user),
            "content": text.as_string(),
        }
        for text in bpy.data.texts
    ],
    "saved": False,
    "cloud_generation_invoked": False,
}, ensure_ascii=False, default=str))
