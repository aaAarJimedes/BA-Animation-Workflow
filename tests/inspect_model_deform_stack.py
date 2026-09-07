from __future__ import annotations

import json
import os

import bpy


if not bpy.app.background or os.environ.get("BAW_DEFORM_STACK_ALLOW") != "read-only-background-test":
    raise RuntimeError("Read-only background opt-in required")

scene = bpy.context.scene
rows = []
for obj in scene.objects:
    if obj.type != "MESH":
        continue
    armature_modifiers = [modifier for modifier in obj.modifiers if modifier.type == "ARMATURE"]
    if not armature_modifiers:
        continue
    keys = obj.data.shape_keys
    rows.append({
        "mesh": obj.name,
        "parent": obj.parent.name if obj.parent else None,
        "parent_type": obj.parent_type,
        "object_scale": list(obj.scale),
        "world_scale": list(obj.matrix_world.to_scale()),
        "modifiers": [
            {
                "name": modifier.name,
                "type": modifier.type,
                "show_viewport": bool(modifier.show_viewport),
                "target": getattr(getattr(modifier, "object", None), "name", None),
                "use_vertex_groups": bool(getattr(modifier, "use_vertex_groups", False)),
                "use_deform_preserve_volume": bool(getattr(modifier, "use_deform_preserve_volume", False)),
            }
            for modifier in obj.modifiers
        ],
        "shape_keys_nonzero": [
            {"name": block.name, "value": float(block.value)}
            for block in keys.key_blocks
            if abs(float(block.value)) > 1e-6
        ] if keys else [],
        "foot_groups": [
            group.name
            for group in obj.vertex_groups
            if any(word in group.name.casefold() for word in ("足首", "つま先", "foot", "toe", "ankle"))
        ],
    })

print("BAW_DEFORM_STACK=" + json.dumps({
    "file": bpy.data.filepath,
    "scene": scene.name,
    "meshes": rows,
    "saved": False,
}, ensure_ascii=False))
