from __future__ import annotations

import os
from pathlib import Path
import re

import bpy
from mathutils import Vector


if not bpy.app.background:
    raise RuntimeError("Foot diagnosis render refuses to run in Blender UI")
if os.environ.get("BAW_FOOT_RENDER_ALLOW") != "read-only-background-test":
    raise RuntimeError("Set BAW_FOOT_RENDER_ALLOW=read-only-background-test explicitly")

output = Path(os.environ["BAW_FOOT_RENDER_OUTPUT"])
output.mkdir(parents=True, exist_ok=True)
scene = bpy.context.scene
target = next(
    obj
    for obj in scene.objects
    if obj.type == "ARMATURE"
    and obj.animation_data is not None
    and (
        (obj.animation_data.action and obj.animation_data.action.get("bam_role") == "RETARGET_OUTPUT")
        or any(
            strip.action and strip.action.get("bam_role") == "RETARGET_OUTPUT"
            for track in obj.animation_data.nla_tracks
            for strip in track.strips
        )
    )
)


def iter_fcurves(action):
    if action is None:
        return
    legacy = getattr(action, "fcurves", None)
    if legacy is not None:
        yield from legacy
        return
    for layer in action.layers:
        for strip in layer.strips:
            for slot in action.slots:
                try:
                    bag = strip.channelbag(slot)
                except (AttributeError, RuntimeError, TypeError):
                    bag = None
                if bag is not None:
                    yield from bag.fcurves


def active_action_at(frame):
    animation = target.animation_data
    if animation.use_nla:
        for track in animation.nla_tracks:
            for strip in track.strips:
                if strip.action and strip.frame_start <= frame <= strip.frame_end:
                    return strip.action
    return animation.action


def mute_rows(action, needle):
    rows = []
    for curve in iter_fcurves(action):
        if needle in curve.data_path and "rotation_" in curve.data_path:
            rows.append((curve, bool(curve.mute)))
            curve.mute = True
    return rows


def restore(rows):
    for curve, mute in rows:
        curve.mute = mute


old_camera = scene.camera
camera_data = old_camera.data.copy() if old_camera else bpy.data.cameras.new("BAW_Foot_Diagnosis_Data")
camera = bpy.data.objects.new("BAW_Foot_Diagnosis_Camera", camera_data)
scene.collection.objects.link(camera)
scene.camera = camera
camera.data.lens = 70.0
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 640
scene.render.resolution_y = 480
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"

for frame in (75, 180, 260):
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    foot_points = [
        target.matrix_world @ target.pose.bones[name].head
        for name in ("足首.L", "足首.R", "つま先.L", "つま先.R")
        if name in target.pose.bones
    ]
    center = sum(foot_points, Vector()) / len(foot_points)
    if old_camera:
        direction = (old_camera.matrix_world.translation - center).normalized()
    else:
        direction = Vector((0.0, -1.0, 0.25)).normalized()
    separation = max((point - center).length for point in foot_points)
    camera.location = center + direction * max(0.65, separation * 7.0)
    camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()

    action = active_action_at(frame)
    for label, needle in (("actual", None), ("no_toe", "つま先"), ("no_ankle", "足首")):
        rows = mute_rows(action, needle) if needle else []
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        scene.render.filepath = str(output / f"foot_{frame:04d}_{label}.png")
        bpy.ops.render.render(write_still=True)
        restore(rows)

scene.camera = old_camera
print(f"BAW_FOOT_RENDER=PASS output={output} saved=False cloud_generation_invoked=False")
