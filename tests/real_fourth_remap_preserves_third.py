"""Remap the fourth Clip locally and verify the third NLA strip survives."""

from __future__ import annotations

import importlib
import json
import os

import bpy


auto_director = importlib.import_module(
    os.environ.get("BAW_AUTO_ADDON_MODULE", "ba_animation_workflow") + ".auto_director"
)

if os.environ.get("BAW_FOURTH_REMAP_ALLOW") != "read-only-background-test":
    raise RuntimeError("Set BAW_FOURTH_REMAP_ALLOW=read-only-background-test explicitly")

scene = bpy.context.scene
settings = scene.baw_auto_director
target = settings.reuse_target_rig or settings.target_rig
if target is None or target.type != "ARMATURE":
    raise AssertionError("Saved project has no reuse target")
animation = target.animation_data
if animation is None:
    raise AssertionError("Reuse target has no animation data")


def bounds(action):
    return auto_director._clip_motion_bounds(action)


third_strips = [
    strip
    for track in animation.nla_tracks
    if track.name.startswith("BAW_上一段_")
    for strip in track.strips
    if (int(round(strip.frame_start)), int(round(strip.frame_end))) == (224, 293)
]
if len(third_strips) != 1:
    raise AssertionError(f"Expected one third-Clip strip, got {len(third_strips)}")
third_strip = third_strips[0]
third_action = third_strip.action
if third_action is None or bounds(third_action) != (224, 293):
    raise AssertionError("Third-Clip strip was not repaired before remap")

fourth_actions = [
    action
    for action in bpy.data.actions
    if auto_director._is_retarget_output_action(action)
    and action.get("bam_target_object") == target.name
    and bounds(action) == (293, 342)
]
if len(fourth_actions) != 1:
    raise AssertionError(f"Expected one current fourth output, got {[action.name for action in fourth_actions]}")
selected = fourth_actions[0]
source = auto_director._find_linked_source_action(selected)
prompt_text = auto_director._find_linked_prompt_text(settings, selected, source)
if source is None or prompt_text is None:
    raise AssertionError("Fourth output is missing its source/Text link")

settings.remap_action = selected
settings.remap_prompt_text = prompt_text
settings.reuse_target_rig = target
result = bpy.ops.baw.auto_remap_existing("EXEC_DEFAULT", action_name=selected.name)
if result != {"FINISHED"}:
    raise AssertionError(f"Fourth local remap failed: {result}; {settings.status_message}")

new_fourth = settings.remap_action
if new_fourth is None or bounds(new_fourth) != (293, 342):
    raise AssertionError("Fourth remap did not produce the expected Clip")
if third_strip.action != third_action or bounds(third_strip.action) != (224, 293):
    raise AssertionError("Fourth remap replaced the third-Clip NLA Action")
if any(
    bounds(strip.action) != (
        int(round(float(strip.action_frame_start))),
        int(round(float(strip.action_frame_end))),
    )
    for track in animation.nla_tracks
    if track.name.startswith("BAW_上一段_")
    for strip in track.strips
    if strip.action is not None
    and int(round(float(strip.action_frame_start))) >= 224
):
    raise AssertionError("A BA-owned NLA strip references an Action from another Clip range")

print(
    "BAW_FOURTH_REMAP_PRESERVES_THIRD="
    + json.dumps(
        {
            "status": "PASS",
            "file": bpy.data.filepath,
            "target": target.name,
            "third_action": third_action.name,
            "third_bounds": bounds(third_action),
            "fourth_action": new_fourth.name,
            "fourth_bounds": bounds(new_fourth),
            "saved": False,
            "cloud_generation_invoked": False,
        },
        ensure_ascii=False,
    )
)
