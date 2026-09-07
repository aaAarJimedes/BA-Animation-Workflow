"""Inspect third/fourth target references after a reuse operation, without saving."""

from __future__ import annotations

import importlib
import json
import os

import bpy


auto_director = importlib.import_module(
    os.environ.get("BAW_AUTO_ADDON_MODULE", "ba_animation_workflow") + ".auto_director"
)

if os.environ.get("BAW_OVERWRITE_DIAG_ALLOW") != "read-only-background-test":
    raise RuntimeError("Set BAW_OVERWRITE_DIAG_ALLOW=read-only-background-test explicitly")

scene = bpy.context.scene
settings = scene.baw_auto_director
target = settings.reuse_target_rig or settings.target_rig
animation = getattr(target, "animation_data", None) if target is not None else None


def bounds(action):
    return list(auto_director._clip_motion_bounds(action))


def action_row(action):
    return {
        "name": action.name,
        "bounds": bounds(action),
        "owner": action.get("bam_target_object"),
        "source": action.get("baw_source_action"),
        "text": action.get("baw_prompt_text"),
        "clip_id": action.get("baw_clip_id"),
        "replaced_by": action.get("baw_replaced_by"),
        "users": action.users,
        "fake_user": action.use_fake_user,
    }


target_actions = [
    action_row(action)
    for action in bpy.data.actions
    if action.get("bam_target_object") == getattr(target, "name", None)
    and bounds(action)[0] >= 224
]
strips = []
if animation is not None:
    for track in animation.nla_tracks:
        for strip in track.strips:
            strips.append(
                {
                    "track": track.name,
                    "strip": strip.name,
                    "action": strip.action.name if strip.action is not None else None,
                    "frame": [float(strip.frame_start), float(strip.frame_end)],
                    "action_frame": [float(strip.action_frame_start), float(strip.action_frame_end)],
                    "mute": bool(track.mute or strip.mute),
                }
            )

texts = {}
for name in ("第三段", "第四段", "第四段.001"):
    text = bpy.data.texts.get(name)
    if text is not None:
        texts[name] = {
            key: text[key]
            for key in text.keys()
            if str(key).startswith("baw_")
        }

print(
    "BAW_THIRD_FOURTH_DIAG="
    + json.dumps(
        {
            "file": bpy.data.filepath,
            "frame": scene.frame_current,
            "target": target.name if target is not None else None,
            "active": animation.action.name if animation and animation.action else None,
            "use_nla": bool(animation.use_nla) if animation else None,
            "strips": strips,
            "target_actions": target_actions,
            "texts": texts,
            "saved": False,
            "cloud_generation_invoked": False,
        },
        ensure_ascii=False,
        default=str,
    )
)
