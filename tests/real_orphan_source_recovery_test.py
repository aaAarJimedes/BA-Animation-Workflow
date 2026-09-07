"""Recover an accepted Proscenium Action that has no target retarget output."""

from __future__ import annotations

import json
import importlib
import os

import bpy

auto_director = importlib.import_module(
    os.environ.get("BAW_AUTO_ADDON_MODULE", "ba_animation_workflow") + ".auto_director"
)


if not bpy.app.background:
    raise RuntimeError("Real orphan recovery test refuses to run in Blender UI")
if os.environ.get("BAW_ORPHAN_RECOVERY_ALLOW") != "read-only-background-test":
    raise RuntimeError("Set BAW_ORPHAN_RECOVERY_ALLOW=read-only-background-test explicitly")

scene = bpy.context.scene
settings = scene.baw_auto_director
bridge = scene.ba_motion_bridge_settings


def clip_bounds(action):
    return (
        int(round(float(action.get("bam_motion_frame_start", action.frame_range[0])))),
        int(round(float(action.get("bam_motion_frame_end", action.frame_range[1])))),
    )


orphans = [action for action in bpy.data.actions if auto_director._is_orphan_source_action(action)]
if len(orphans) != 1:
    raise AssertionError(f"Expected exactly one orphan source Action, got {[action.name for action in orphans]}")
orphan = orphans[0]
if clip_bounds(orphan) != (293, 342):
    raise AssertionError(f"Unexpected orphan range: {clip_bounds(orphan)}")

target = settings.reuse_target_rig
if target is None or target.type != "ARMATURE":
    raise AssertionError("Saved project has no selected recovery target")
animation = target.animation_data
if animation is None:
    raise AssertionError("Recovery target has no preceding animation")

scene.frame_set(293)
bpy.context.view_layer.update()
seam_bones = [name for name in ("センター", "グルーブ", "下半身") if name in target.pose.bones]
pose_before = {name: target.pose.bones[name].matrix.copy() for name in seam_bones}
old_actions = {action.as_pointer() for action in bpy.data.actions}

fourth_text = bpy.data.texts.get("第四段")
if fourth_text is None:
    raise AssertionError("Saved project has no 第四段 Text")
wrong_actions = [
    action
    for action in bpy.data.actions
    if action.get("baw_prompt_text") == fourth_text.name
    and auto_director._find_linked_source_action(action) is not None
    and not auto_director._prompt_keys_match(
        fourth_text.as_string(),
        auto_director._source_prompt_key(auto_director._find_linked_source_action(action)),
    )
]
if not wrong_actions:
    raise AssertionError("Saved project no longer contains the stale third-Action regression fixture")
stale_action = sorted(wrong_actions, key=lambda action: action.name)[-1]
settings.remap_prompt_syncing = True
try:
    settings.remap_prompt_text = fourth_text
    settings.remap_action = stale_action
finally:
    settings.remap_prompt_syncing = False
if settings.remap_prompt_text is None or settings.remap_prompt_text.name != "第四段":
    raise AssertionError(
        f"Orphan source did not recover its prompt Text: {getattr(settings.remap_prompt_text, 'name', None)}"
    )
result = bpy.ops.baw.auto_import_existing("EXEC_DEFAULT", action_name=stale_action.name)
if result != {"FINISHED"}:
    raise AssertionError(f"Orphan recovery failed: {result}; {settings.status_message}")

new_action = settings.remap_action
if new_action is None or new_action.as_pointer() in old_actions:
    raise AssertionError("Orphan recovery did not create and select a new target Action")
if clip_bounds(new_action) != (293, 342):
    raise AssertionError(f"Recovered Clip range is wrong: {clip_bounds(new_action)}")
if new_action.get("baw_source_action") != orphan.name:
    raise AssertionError("Recovered target Action is not linked to the orphan source")
if new_action.get("baw_prompt_text") != "第四段":
    raise AssertionError("Recovered target Action lost the fourth prompt Text")
if new_action.get("bam_target_object") != target.name:
    raise AssertionError("Recovered target Action belongs to the wrong model")

scene.frame_set(293)
bpy.context.view_layer.update()
seam_error = max(
    (
        max(
            abs(float(target.pose.bones[name].matrix[row][column]) - float(pose_before[name][row][column]))
            for row in range(4)
            for column in range(4)
        )
        for name in seam_bones
    ),
    default=0.0,
)
if seam_error >= 2e-4:
    raise AssertionError(f"Recovered fourth Clip broke the 293-frame seam: {seam_error}")

print(
    "BAW_ORPHAN_RECOVERY="
    + json.dumps(
        {
            "status": "PASS",
            "file": bpy.data.filepath,
            "source": orphan.name,
            "target": target.name,
            "output": new_action.name,
            "bounds": clip_bounds(new_action),
            "prompt_text": new_action.get("baw_prompt_text"),
            "seam_error": seam_error,
            "saved": False,
            "cloud_generation_invoked": False,
        },
        ensure_ascii=False,
    )
)
