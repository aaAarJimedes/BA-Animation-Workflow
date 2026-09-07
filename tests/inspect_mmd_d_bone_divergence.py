from __future__ import annotations

import json
import os

import bpy


if not bpy.app.background or os.environ.get("BAW_D_BONE_ALLOW") != "read-only-background-test":
    raise RuntimeError("Read-only background opt-in required")

scene = bpy.context.scene
target = bpy.data.objects.get("伊落玛丽 _arm.002")
mesh = bpy.data.objects.get("伊落玛丽 _mesh")
if target is None or mesh is None:
    raise RuntimeError("Expected animated comparison model is missing")


def matrix_error(left, right):
    return max(
        abs(float(left[row][column]) - float(right[row][column]))
        for row in range(4)
        for column in range(4)
    )


bone_pairs = (
    ("足.L", "足D.L"),
    ("ひざ.L", "ひざD.L"),
    ("足首.L", "足首D.L"),
    ("足.R", "足D.R"),
    ("ひざ.R", "ひざD.R"),
    ("足首.R", "足首D.R"),
)
samples = []
for frame in (1, 75, 149, 150, 180, 223, 224, 260, 293):
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    rows = []
    for main_name, deform_name in bone_pairs:
        main = target.pose.bones.get(main_name)
        deform = target.pose.bones.get(deform_name)
        if main is None or deform is None:
            continue
        main_delta = main.matrix @ main.bone.matrix_local.inverted_safe()
        deform_delta = deform.matrix @ deform.bone.matrix_local.inverted_safe()
        rows.append({
            "main": main_name,
            "deform": deform_name,
            "delta_matrix_error": matrix_error(main_delta, deform_delta),
            "main_scale": list(main_delta.to_scale()),
            "deform_scale": list(deform_delta.to_scale()),
            "rotation_difference_degrees": main_delta.to_quaternion().rotation_difference(
                deform_delta.to_quaternion()
            ).angle * 57.29577951308232,
            "translation_difference": (main_delta.translation - deform_delta.translation).length,
        })
    samples.append({"frame": frame, "pairs": rows})

group_names = {group.index: group.name for group in mesh.vertex_groups}
weight_rows = []
for side in ("L", "R"):
    relevant = {f"足首.{side}", f"足首D.{side}", f"つま先.{side}"}
    counts = {name: 0 for name in relevant}
    sums = {name: 0.0 for name in relevant}
    both_ankles = 0
    vertices = 0
    for vertex in mesh.data.vertices:
        weights = {
            group_names.get(member.group, ""): float(member.weight)
            for member in vertex.groups
            if group_names.get(member.group, "") in relevant and member.weight > 1e-6
        }
        if not weights:
            continue
        vertices += 1
        for name, weight in weights.items():
            counts[name] += 1
            sums[name] += weight
        if f"足首.{side}" in weights and f"足首D.{side}" in weights:
            both_ankles += 1
    weight_rows.append({
        "side": side,
        "vertices": vertices,
        "counts": counts,
        "weight_sums": sums,
        "vertices_weighted_to_both_ankles": both_ankles,
    })

print("BAW_D_BONE_DIVERGENCE=" + json.dumps({
    "file": bpy.data.filepath,
    "target": target.name,
    "samples": samples,
    "weights": weight_rows,
    "saved": False,
}, ensure_ascii=False))
