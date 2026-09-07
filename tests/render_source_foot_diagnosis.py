from __future__ import annotations

import os
from pathlib import Path

import bpy
from mathutils import Vector


if not bpy.app.background or os.environ.get("BAW_SOURCE_FOOT_ALLOW") != "read-only-background-test":
    raise RuntimeError("Read-only background opt-in required")

output = Path(os.environ["BAW_SOURCE_FOOT_OUTPUT"])
output.mkdir(parents=True, exist_ok=True)
scene = bpy.context.scene
target = bpy.data.objects["伊落玛丽 _arm.002"]
source = bpy.data.objects["kimodo-soma-rp"]
source_body = bpy.data.objects.get("kimodo-soma-rp_body")
old_camera = scene.camera
old_source_action = source.animation_data.action
old_source_nla = bool(source.animation_data.use_nla)
old_hide = bool(source_body.hide_render) if source_body else False

camera_data = old_camera.data.copy() if old_camera else bpy.data.cameras.new("BAW_Source_Foot_Data")
camera = bpy.data.objects.new("BAW_Source_Foot_Camera", camera_data)
scene.collection.objects.link(camera)
scene.camera = camera
camera.data.lens = 70.0
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 640
scene.render.resolution_y = 480
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"

if source_body:
    source_body.hide_render = False
for frame in (75, 180, 260):
    target_action = target.animation_data.action
    if target.animation_data.use_nla:
        for track in target.animation_data.nla_tracks:
            for strip in track.strips:
                if strip.action and strip.frame_start <= frame <= strip.frame_end:
                    target_action = strip.action
                    break
    source_action = bpy.data.actions.get(str(target_action.get("baw_source_action", "") or ""))
    source.animation_data.action = source_action
    source.animation_data.use_nla = False
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    names = ("LeftFoot", "RightFoot", "LeftToeBase", "RightToeBase")
    points = [source.matrix_world @ source.pose.bones[name].head for name in names]
    center = sum(points, Vector()) / len(points)
    direction = Vector((0.0, -1.0, 0.18)).normalized()
    separation = max((point - center).length for point in points)
    camera.location = center + direction * max(0.8, separation * 6.5)
    camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = str(output / f"source_foot_{frame:04d}.png")
    bpy.ops.render.render(write_still=True)

source.animation_data.action = old_source_action
source.animation_data.use_nla = old_source_nla
if source_body:
    source_body.hide_render = old_hide
scene.camera = old_camera
print(f"BAW_SOURCE_FOOT_RENDER=PASS output={output} saved=False cloud_generation_invoked=False")
