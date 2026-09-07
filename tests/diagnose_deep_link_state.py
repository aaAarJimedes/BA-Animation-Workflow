"""Inspect stale Text/Action metadata in the saved Kitchen project without saving."""

from __future__ import annotations

import importlib
import json
import os

import bpy


auto_director = importlib.import_module(
    os.environ.get("BAW_AUTO_ADDON_MODULE", "ba_animation_workflow") + ".auto_director"
)

if os.environ.get("BAW_DEEP_LINK_DIAG_ALLOW") != "read-only-background-test":
    raise RuntimeError("Set BAW_DEEP_LINK_DIAG_ALLOW=read-only-background-test explicitly")

scene = bpy.context.scene
settings = scene.baw_auto_director
text = bpy.data.texts.get("第四段")
target = settings.reuse_target_rig


def props(value):
    return {
        str(key): value[key]
        for key in value.keys()
        if str(key).startswith("baw_") or str(key).startswith("bam_")
    }


rows = []
for action in bpy.data.actions:
    if not (
        action.name.startswith("Proscenium_Motion:")
        or action.get("baw_prompt_text") in {"第四段", "第四段.001"}
    ):
        continue
    linked = auto_director._find_linked_source_action(action)
    rows.append(
        {
            "name": action.name,
            "accepted_source": auto_director._is_proscenium_source_action(action),
            "orphan_source": auto_director._is_orphan_source_action(action),
            "linked_source": linked.name if linked is not None else None,
            "matches_fourth": auto_director._action_matches_text(action, text),
            "props": props(action),
        }
    )

resolved = auto_director._resolve_text_action(
    scene,
    settings,
    text,
    target=target,
    persist=False,
)
print(
    "BAW_DEEP_LINK_DIAG="
    + json.dumps(
        {
            "text_props": props(text),
            "target": target.name if target is not None else None,
            "saved_selected": getattr(settings.remap_action, "name", None),
            "resolved": resolved.name if resolved is not None else None,
            "actions": rows,
            "saved": False,
            "cloud_generation_invoked": False,
        },
        ensure_ascii=False,
        default=str,
    )
)
