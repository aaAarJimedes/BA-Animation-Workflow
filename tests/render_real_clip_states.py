from __future__ import annotations

import importlib
import json
import os
from pathlib import Path

import bpy


def render(label: str, frames: tuple[int, ...]) -> None:
    for frame in frames:
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        scene.render.filepath = str(output / f"{label}_{frame:04d}.png")
        bpy.ops.render.render(write_still=True)


if not bpy.app.background:
    raise RuntimeError("Real Clip renderer refuses to run in Blender UI")
if os.environ.get("BAW_REAL_RENDER_ALLOW") != "read-only-background-test":
    raise RuntimeError("Set BAW_REAL_RENDER_ALLOW=read-only-background-test explicitly")

output = Path(os.environ["BAW_REAL_RENDER_OUTPUT"])
output.mkdir(parents=True, exist_ok=True)
fixed_only = os.environ.get("BAW_REAL_RENDER_FIXED_ONLY") == "1"
saved_only = os.environ.get("BAW_REAL_RENDER_SAVED_ONLY") == "1"
scene = bpy.context.scene
settings = scene.baw_auto_director
target = settings.target_rig
animation_data = target.animation_data
new_action = animation_data.action
boundary = int(round(float(new_action.frame_range[0])))
clip_end = int(round(float(new_action.frame_range[1])))
old_strip = next(
    strip
    for track in animation_data.nla_tracks
    if track.name.startswith("BAW_上一段_")
    for strip in track.strips
    if int(round(float(strip.frame_end))) == boundary
)
old_action = old_strip.action

scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 640
scene.render.resolution_y = 360
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.film_transparent = False

animation_data.action = new_action
animation_data.use_nla = True
if not fixed_only:
    render("saved_combined", (boundary - 1, boundary, boundary + 1, boundary + 30, clip_end))
if saved_only:
    print("BAW_REAL_RENDER=" + json.dumps({
        "status": "PASS",
        "output": str(output),
        "boundary": boundary,
        "saved": False,
        "cloud_generation_invoked": False,
    }, ensure_ascii=False))
    raise SystemExit(0)

animation_data.action = None
animation_data.use_nla = True
if not fixed_only:
    render("previous_only", (boundary - 1, boundary))
scene.frame_set(boundary)
bpy.context.view_layer.update()
continuity_json = importlib.import_module(
    os.environ.get("BAW_AUTO_ADDON_MODULE", "bl_ext.user_default.ba_animation_workflow")
    + ".auto_director"
)._capture_current_pose(target)

animation_data.action = new_action
animation_data.use_nla = False
if not fixed_only:
    render("new_only", (boundary, boundary + 1, boundary + 30, clip_end))

auto_director = importlib.import_module(
    os.environ.get("BAW_AUTO_ADDON_MODULE", "bl_ext.user_default.ba_animation_workflow")
    + ".auto_director"
)
settings.start_behavior = "CURRENT_POSE"
settings.motion_start_frame = boundary
settings.continuity_pose_json = continuity_json
settings.previous_clip_action = old_action
settings.previous_clip_action_name = old_action.name
settings.previous_clip_use_nla = True
animation_data.action = new_action
animation_data.use_nla = True
auto_director._preserve_previous_clip(settings, new_action)
auto_director._apply_continuity_pose(scene, settings, new_action)
render("fixed_current", (boundary - 1, boundary, boundary + 1, boundary + 30, clip_end))

print("BAW_REAL_RENDER=" + json.dumps({
    "status": "PASS",
    "output": str(output),
    "boundary": boundary,
    "saved": False,
    "cloud_generation_invoked": False,
}, ensure_ascii=False))
