from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
import sys

import bpy


WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.environ.get("BAW_PROMPT_IMPORT_ROOT", str(WORKSPACE / "extension")))

module_name = os.environ.get("BAW_PROMPT_ADDON_MODULE", "ba_animation_workflow")
addon = importlib.import_module(module_name)
if not hasattr(bpy.types.Scene, "baw_auto_director"):
    addon.register()

path = Path(os.environ["BAW_PROMPT_CASE"])
settings = bpy.context.scene.baw_auto_director
prompt = path.read_text(encoding="utf-8")
auto_director = importlib.import_module(module_name + ".auto_director")
settings.creative_prompt = prompt
settings.total_frames = int(os.environ.get("BAW_PROMPT_TOTAL_FRAMES", "150"))
bpy.context.scene.render.fps = int(os.environ.get("BAW_PROMPT_SCENE_FPS", "30"))
bpy.context.scene.render.fps_base = 1.0
placement = int(os.environ.get("BAW_PROMPT_START_FRAME", "1"))
plan = auto_director.compile_plan(settings, placement_frame=placement)

result = {
    "fps": plan["fps"],
    "frame_start": plan["frame_start"],
    "frame_end": plan["frame_end"],
    "duration_seconds": plan["duration_seconds"],
    "batches": len(plan["generation_batches"]),
    "prompt_blocks": len(plan["prompt_blocks"]),
    "pose_anchors": len(plan["pose_anchors"]),
    "timing_sources": plan["timing_sources"],
    "batch_ranges": [
        [batch["global_frame_start"], batch["global_frame_end"]]
        for batch in plan["generation_batches"]
    ],
}
print("BAW_PROMPT_CASE=" + json.dumps(result, ensure_ascii=False))
