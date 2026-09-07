from __future__ import annotations

import json
import os

import bpy


if not bpy.app.background:
    raise RuntimeError("Boundary diagnosis refuses to run in Blender UI")
if os.environ.get("BAW_BOUNDARY_INSPECT_ALLOW") != "read-only-background-test":
    raise RuntimeError("Set BAW_BOUNDARY_INSPECT_ALLOW=read-only-background-test explicitly")

scene = bpy.context.scene
target = scene.baw_auto_director.target_rig
animation_data = target.animation_data
active_action = animation_data.action
use_nla = bool(animation_data.use_nla)


def values(vector):
    return [round(float(value), 9) for value in vector]


def pose(frame, action, nla=False):
    animation_data.action = action
    animation_data.use_nla = nla
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    evaluated = target.evaluated_get(bpy.context.evaluated_depsgraph_get())
    return {
        name: {
            "basis": values(target.pose.bones[name].location),
            "visible": values(evaluated.pose.bones[name].matrix.translation),
            "world": values(target.matrix_world @ evaluated.pose.bones[name].matrix.translation),
        }
        for name in ("センター", "グルーブ", "下半身")
    }


strips = sorted(
    (strip for track in animation_data.nla_tracks for strip in track.strips),
    key=lambda strip: strip.frame_start,
)
seams = []
for index, previous_strip in enumerate(strips):
    seam = int(round(previous_strip.frame_end))
    next_action = (
        strips[index + 1].action
        if index + 1 < len(strips) and int(round(strips[index + 1].frame_start)) == seam
        else active_action
    )
    previous_action = previous_strip.action
    seams.append({
        "seam": seam,
        "previous": previous_action.name,
        "next": next_action.name if next_action else None,
        "previous_at_minus_one": pose(seam - 1, previous_action),
        "previous_at_seam": pose(seam, previous_action),
        "next_at_seam": pose(seam, next_action),
        "next_at_plus_one": pose(seam + 1, next_action),
    })

animation_data.action = active_action
animation_data.use_nla = use_nla
combined = {
    str(frame): pose(frame, active_action, use_nla)
    for frame in (149, 150, 223, 224)
}
animation_data.action = active_action
animation_data.use_nla = use_nla

print("BAW_BOUNDARY_ROOT=" + json.dumps({
    "status": "PASS",
    "file": bpy.data.filepath,
    "seams": seams,
    "combined": combined,
    "saved": False,
    "cloud_generation_invoked": False,
}, ensure_ascii=False))
