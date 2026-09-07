from __future__ import annotations

import json

import bpy


scene = bpy.context.scene
settings = getattr(scene, "baw_auto_director", None)
proscenium = getattr(scene, "proscenium", None)

payload = {
    "file": bpy.data.filepath,
    "scene": {
        "fps": scene.render.fps,
        "fps_base": scene.render.fps_base,
        "frame_start": scene.frame_start,
        "frame_end": scene.frame_end,
    },
    "auto_director": None,
    "proscenium": None,
    "actions": [],
}

if settings is not None:
    payload["auto_director"] = {
        "creative_prompt": settings.creative_prompt,
        "total_frames": settings.total_frames,
        "state": settings.state,
        "status_message": settings.status_message,
        "plan_json": settings.plan_json,
        "plan_text_name": settings.plan_text_name,
    }

if proscenium is not None:
    payload["proscenium"] = {
        "target_armature": getattr(getattr(proscenium, "target_armature", None), "name", None),
        "is_generating": bool(getattr(proscenium, "is_generating", False)),
        "is_previewing": bool(getattr(proscenium, "is_previewing", False)),
        "prompt_blocks": [
            {
                "frame_start": block.frame_start,
                "frame_end": block.frame_end,
                "prompt": block.prompt,
                "enabled": block.enabled,
            }
            for block in getattr(proscenium, "prompt_blocks", ())
        ],
    }

for action in bpy.data.actions:
    slot_ranges = []
    for slot in getattr(action, "slots", ()):
        channelbag = action.layers[0].strips[0].channelbag(slot) if action.layers and action.layers[0].strips else None
        if channelbag is None:
            continue
        frames = [point.co[0] for curve in channelbag.fcurves for point in curve.keyframe_points]
        if frames:
            slot_ranges.append({
                "slot": getattr(slot, "identifier", getattr(slot, "display_name", "")),
                "min": min(frames),
                "max": max(frames),
                "keys": len(frames),
            })
    payload["actions"].append({"name": action.name, "frame_range": list(action.frame_range), "slot_ranges": slot_ranges})

print("BAW_TIMING_INSPECTION=" + json.dumps(payload, ensure_ascii=False))
