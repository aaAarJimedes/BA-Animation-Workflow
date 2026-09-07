from __future__ import annotations

import importlib
import os

import bpy


if not bpy.app.background:
    raise RuntimeError("Legacy migration test is background-only")

module = importlib.import_module(os.environ["BAW_ADDON_MODULE"])
constants = importlib.import_module(os.environ["BAW_ADDON_MODULE"] + ".constants")
if not hasattr(bpy.types.Scene, "baw_settings"):
    module.register()

scene = bpy.context.scene
for obj in tuple(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)
for collection in tuple(bpy.data.collections):
    bpy.data.collections.remove(collection)

root = bpy.data.collections.new("BAW_PIPELINE")
scene.collection.children.link(root)
children = {}
for name in constants.COLLECTIONS:
    child = bpy.data.collections.new(name)
    root.children.link(child)
    children[name] = child

legacy_light_data = bpy.data.lights.new("BAW_Key", type="AREA")
legacy_light_data.energy = 17.0
legacy_light = bpy.data.objects.new("BAW_Key", legacy_light_data)
legacy_light["baw_generated"] = True
children["BAW_50_LIGHTS"].objects.link(legacy_light)

poisoned_camera_data = bpy.data.cameras.new("UserCameraData")
poisoned_camera_data.lens = 12.0
poisoned_camera = bpy.data.objects.new("BAW_Camera", poisoned_camera_data)
poisoned_camera["baw_generated"] = True
children["BAW_60_CAMERAS"].objects.link(poisoned_camera)

if bpy.ops.baw.setup_scene() != {"FINISHED"}:
    raise AssertionError("Legacy Scene migration operator failed")

scene_id = scene.get("baw_scene_id")
if not scene_id or scene.get("baw_migrated_from") != "0.1.0":
    raise AssertionError("Legacy Scene migration was not recorded")
if root.get("baw_owner") != "ba_animation_workflow" or root.get("baw_scene_id") != scene_id:
    raise AssertionError("Legacy root was not safely claimed")
if legacy_light.get("baw_owner") is not None or legacy_light_data.get("baw_owner") is not None:
    raise AssertionError("Legacy object or data was unsafely claimed")
if poisoned_camera.get("baw_owner") is not None or poisoned_camera_data.get("baw_owner") is not None:
    raise AssertionError("Poisoned legacy camera was claimed")
if sum(1 for item in bpy.data.collections if item.get("baw_role") == "BAW_PIPELINE") != 1:
    raise AssertionError("Legacy migration created a duplicate pipeline")

if bpy.ops.baw.create_light_rig() != {"FINISHED"}:
    raise AssertionError("Safe light regeneration failed")
if bpy.ops.baw.create_camera_rig() != {"FINISHED"}:
    raise AssertionError("Safe camera regeneration failed")
if abs(legacy_light_data.energy - 17.0) > 1e-6:
    raise AssertionError("Legacy light data was modified")
if abs(poisoned_camera_data.lens - 12.0) > 1e-6:
    raise AssertionError("Poisoned user camera data was modified")
owned_camera = module.utils.find_owned_object("BAW_Camera", children["BAW_60_CAMERAS"], "CAMERA")
if owned_camera is None or owned_camera == poisoned_camera:
    raise AssertionError("A separate owned camera was not created")

print("BAW_LEGACY_SCENE_MIGRATION=PASS")
