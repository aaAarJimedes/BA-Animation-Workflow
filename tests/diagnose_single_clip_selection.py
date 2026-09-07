"""Inspect whether the single-Clip reuse selector depends on the playhead."""

from __future__ import annotations

import json
import os

import bpy


if not bpy.app.background:
    raise RuntimeError("Selection diagnosis refuses to run in Blender UI")
if os.environ.get("BAW_REAL_REUSE_ALLOW") != "read-only-background-test":
    raise RuntimeError("Set BAW_REAL_REUSE_ALLOW=read-only-background-test explicitly")

scene = bpy.context.scene
settings = scene.baw_auto_director


def bounds(action):
    return (
        int(round(float(action.get("bam_motion_frame_start", action.frame_range[0])))),
        int(round(float(action.get("bam_motion_frame_end", action.frame_range[1])))),
    )


actions = sorted(
    (
        action
        for action in bpy.data.actions
        if action.get("bam_role") == "RETARGET_OUTPUT"
        and not action.get("baw_replaced_by")
    ),
    key=lambda action: (*bounds(action), action.name),
)
owners = {}
for action in actions:
    owners.setdefault(str(action.get("bam_target_object", "") or ""), []).append(action)
actions = max(owners.values(), key=len)

frames = sorted({scene.frame_start, scene.frame_current} | {value for action in actions for value in bounds(action)})
rows = []
for frame in frames:
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    for action in actions:
        settings.remap_action = action
        rows.append(
            {
                "frame": frame,
                "requested": action.name,
                "selected": getattr(settings.remap_action, "name", None),
                "bounds": bounds(action),
                "stored_source": action.get("baw_source_action"),
                "stored_text": action.get("baw_prompt_text"),
                "resolved_text": getattr(settings.remap_prompt_text, "name", None),
            }
        )

print(
    "BAW_SINGLE_SELECTION_DIAG="
    + json.dumps(
        {
            "file": bpy.data.filepath,
            "owner": str(actions[0].get("bam_target_object", "") or "") if actions else None,
            "actions": len(actions),
            "rows": rows,
            "saved": False,
            "cloud_generation_invoked": False,
        },
        ensure_ascii=False,
    )
)
