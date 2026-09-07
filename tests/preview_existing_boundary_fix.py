from __future__ import annotations

import importlib
import json
import os
from pathlib import Path

import bpy


if not bpy.app.background:
    raise RuntimeError("Boundary-fix preview refuses to run in Blender UI")
if os.environ.get("BAW_BOUNDARY_FIX_ALLOW") != "read-only-background-test":
    raise RuntimeError("Set BAW_BOUNDARY_FIX_ALLOW=read-only-background-test explicitly")

output = Path(os.environ["BAW_BOUNDARY_FIX_OUTPUT"])
output.mkdir(parents=True, exist_ok=True)
module_name = os.environ.get("BAW_AUTO_ADDON_MODULE", "ba_animation_workflow")
auto_director = importlib.import_module(module_name + ".auto_director")
scene = bpy.context.scene
settings = scene.baw_auto_director
target = settings.target_rig
animation_data = target.animation_data
active_action = animation_data.action
use_nla = bool(animation_data.use_nla)
strips = sorted(
    (strip for track in animation_data.nla_tracks for strip in track.strips),
    key=lambda strip: strip.frame_start,
)


def matrix_error(left, right):
    return max(
        abs(float(left[row][column]) - float(right[row][column]))
        for row in range(4)
        for column in range(4)
    )


clips = [strip.action for strip in strips] + [active_action]
seams = [int(round(strip.frame_end)) for strip in strips]
for previous, new_action, seam in zip(clips, clips[1:], seams):
    animation_data.action = previous
    animation_data.use_nla = False
    scene.frame_set(seam)
    bpy.context.view_layer.update()
    continuity_json = auto_director._capture_current_pose(target)
    settings.start_behavior = "CURRENT_POSE"
    settings.motion_start_frame = seam
    settings.continuity_pose_json = continuity_json
    animation_data.action = new_action
    auto_director._apply_continuity_pose(scene, settings, new_action)

seam_errors = []
for previous, new_action, seam in zip(clips, clips[1:], seams):
    animation_data.use_nla = False
    animation_data.action = previous
    scene.frame_set(seam)
    bpy.context.view_layer.update()
    previous_pose = {
        name: target.pose.bones[name].matrix.copy()
        for name in ("センター", "グルーブ", "下半身")
    }
    animation_data.action = new_action
    scene.frame_set(seam)
    bpy.context.view_layer.update()
    errors = {
        name: matrix_error(target.pose.bones[name].matrix, previous_pose[name])
        for name in previous_pose
    }
    seam_errors.append({"seam": seam, "errors": errors})
    if max(errors.values()) >= 2e-5:
        raise AssertionError(f"Visible seam mismatch at {seam}: {errors}")

animation_data.action = active_action
animation_data.use_nla = use_nla
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 640
scene.render.resolution_y = 360
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.film_transparent = False
for frame in (149, 150, 151, 223, 224, 225):
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    scene.render.filepath = str(output / f"boundary_fix_{frame:04d}.png")
    bpy.ops.render.render(write_still=True)

print("BAW_BOUNDARY_FIX=" + json.dumps({
    "status": "PASS",
    "file": bpy.data.filepath,
    "seam_errors": seam_errors,
    "saved": False,
    "cloud_generation_invoked": False,
}, ensure_ascii=False))
