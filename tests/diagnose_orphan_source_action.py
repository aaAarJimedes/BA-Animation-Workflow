"""Inspect generated Proscenium Actions that have no BA retarget output."""

from __future__ import annotations

import json
import os

import bpy


if not bpy.app.background:
    raise RuntimeError("Orphan Action diagnosis refuses to run in Blender UI")
if os.environ.get("BAW_ORPHAN_DIAG_ALLOW") != "read-only-background-test":
    raise RuntimeError("Set BAW_ORPHAN_DIAG_ALLOW=read-only-background-test explicitly")

scene = bpy.context.scene
settings = scene.baw_auto_director
bridge = scene.ba_motion_bridge_settings
proscenium = getattr(scene, "proscenium", None)


def bounds(action):
    return [int(round(float(value))) for value in action.frame_range]


outputs = []
linked_sources = set()
for action in bpy.data.actions:
    if action.get("bam_role") != "RETARGET_OUTPUT":
        continue
    linked = str(action.get("baw_source_action", "") or "")
    if linked:
        linked_sources.add(linked)
    outputs.append(
        {
            "name": action.name,
            "bounds": bounds(action),
            "motion_bounds": [
                int(round(float(action.get("bam_motion_frame_start", action.frame_range[0])))),
                int(round(float(action.get("bam_motion_frame_end", action.frame_range[1])))),
            ],
            "owner": action.get("bam_target_object"),
            "source": linked or None,
            "text": action.get("baw_prompt_text"),
            "replaced_by": action.get("baw_replaced_by"),
        }
    )

source_actions = []
for action in bpy.data.actions:
    if not action.name.startswith("Proscenium_Motion:"):
        continue
    source_actions.append(
        {
            "name": action.name,
            "bounds": bounds(action),
            "users": action.users,
            "fake_user": action.use_fake_user,
            "linked_output": action.name in linked_sources,
        }
    )

source_rig = bridge.source_rig
source_animation = getattr(source_rig, "animation_data", None) if source_rig else None
source_state = {
    "rig": getattr(source_rig, "name", None),
    "active": getattr(getattr(source_animation, "action", None), "name", None),
    "use_nla": bool(source_animation and source_animation.use_nla),
    "strips": [
        {
            "track": track.name,
            "action": getattr(strip.action, "name", None),
            "frame_start": strip.frame_start,
            "frame_end": strip.frame_end,
            "mute": strip.mute,
        }
        for track in (source_animation.nla_tracks if source_animation else ())
        for strip in track.strips
    ],
}

print(
    "BAW_ORPHAN_SOURCE_DIAG="
    + json.dumps(
        {
            "file": bpy.data.filepath,
            "frame": scene.frame_current,
            "timeline": [scene.frame_start, scene.frame_end],
            "target": getattr(settings.target_rig, "name", None),
            "reuse_target": getattr(settings.reuse_target_rig, "name", None),
            "selected_output": getattr(settings.remap_action, "name", None),
            "prompt_text": getattr(settings.prompt_text, "name", None),
            "prompt_preview": settings.prompt_text.as_string()[:160] if settings.prompt_text else None,
            "proscenium": {
                "target": getattr(getattr(proscenium, "target_armature", None), "name", None),
                "is_generating": bool(getattr(proscenium, "is_generating", False)),
                "is_previewing": bool(getattr(proscenium, "is_previewing", False)),
                "source_action_name": str(getattr(proscenium, "source_action_name", "") or ""),
            },
            "bridge": {
                "target": getattr(bridge.target_rig, "name", None),
                "last_output": bridge.last_output_action,
                "previous_state": bridge.previous_target_state_available,
                "previous_target": getattr(bridge.previous_target_rig, "name", None),
            },
            "source_rig": source_state,
            "outputs": sorted(outputs, key=lambda row: (row["motion_bounds"], row["name"])),
            "source_actions": sorted(source_actions, key=lambda row: (row["bounds"], row["name"])),
            "saved": False,
            "cloud_generation_invoked": False,
        },
        ensure_ascii=False,
    )
)
