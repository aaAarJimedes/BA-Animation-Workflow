"""Verify Text-first Action recovery in the saved Kitchen project without saving it."""

from __future__ import annotations

import importlib
import json
import os

import bpy


auto_director = importlib.import_module(
    os.environ.get("BAW_AUTO_ADDON_MODULE", "ba_animation_workflow") + ".auto_director"
)

if not bpy.app.background:
    raise RuntimeError("Real Text/Action link test refuses to run in Blender UI")
if os.environ.get("BAW_TEXT_LINK_ALLOW") != "read-only-background-test":
    raise RuntimeError("Set BAW_TEXT_LINK_ALLOW=read-only-background-test explicitly")

scene = bpy.context.scene
settings = scene.baw_auto_director
text = bpy.data.texts.get("第四段")
if text is None:
    raise AssertionError("Saved project has no 第四段 Text")

target = settings.reuse_target_rig
settings.remap_prompt_text = text
selected = settings.remap_action
if selected is None:
    raise AssertionError("Selecting 第四段 did not resolve an Action")

source = selected if auto_director._is_proscenium_source_action(selected) else auto_director._find_linked_source_action(selected)
if source is None:
    raise AssertionError(f"Resolved Action has no accepted source: {selected.name}")
if not auto_director._prompt_keys_match(text.as_string(), auto_director._source_prompt_key(source)):
    raise AssertionError(f"Resolved Action belongs to another prompt: {selected.name} -> {source.name}")

wrong = []
for action in bpy.data.actions:
    if action.get("baw_prompt_text") != text.name:
        continue
    linked_source = auto_director._find_linked_source_action(action)
    if linked_source is not None and not auto_director._prompt_keys_match(
        text.as_string(), auto_director._source_prompt_key(linked_source)
    ):
        wrong.append(action.name)
if selected.name in wrong:
    raise AssertionError("Text-first lookup selected a legacy mislabelled Action")

print(
    "BAW_REAL_TEXT_ACTION_LINK="
    + json.dumps(
        {
            "status": "PASS",
            "file": bpy.data.filepath,
            "text": text.name,
            "target": target.name if target is not None else None,
            "resolved_action": selected.name,
            "resolved_source": source.name,
            "ignored_mislabelled_actions": wrong,
            "saved": False,
            "cloud_generation_invoked": False,
        },
        ensure_ascii=False,
    )
)
