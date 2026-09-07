from __future__ import annotations

import importlib
import json
import math
import os
from pathlib import Path

import bpy
from mathutils import Quaternion


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def expect_cancelled(callback, message: str, expected_error: str) -> None:
    try:
        result = callback()
    except RuntimeError as exc:
        check(expected_error in str(exc), f"{message}; unexpected error: {exc}")
        return
    check(result == {"CANCELLED"}, message)


def expect_value_error(callback, message: str, expected_error: str) -> None:
    try:
        callback()
    except ValueError as exc:
        check(expected_error in str(exc), f"{message}; unexpected error: {exc}")
        return
    raise AssertionError(f"{message}; ValueError was not raised")


def key_count(action) -> int:
    module = importlib.import_module(os.environ.get("BAW_ADDON_MODULE", "bl_ext.user_default.ba_animation_workflow"))
    return sum(len(curve.keyframe_points) for curve in module.operators.iter_action_fcurves(action))


def main() -> None:
    if not bpy.app.background:
        raise RuntimeError("Smoke test refuses to run in Blender UI")
    if os.environ.get("BAW_SMOKE_ALLOW_DESTRUCTIVE") != "isolated-factory-test":
        raise RuntimeError("Set BAW_SMOKE_ALLOW_DESTRUCTIVE=isolated-factory-test explicitly")

    addon_module = os.environ.get("BAW_ADDON_MODULE", "bl_ext.user_default.ba_animation_workflow")
    module = importlib.import_module(addon_module)
    if not hasattr(bpy.types.Scene, "baw_settings"):
        module.register()
    camera_rig_module = os.environ.get("BAW_CAMERA_RIG_MODULE")
    if camera_rig_module:
        result = bpy.ops.preferences.addon_enable(module=camera_rig_module)
        check(result == {"FINISHED"}, "Could not enable Add Camera Rigs in factory profile")

    test_root = Path(os.environ["BAW_TEST_PROJECT"]).resolve()
    if test_root.exists():
        raise RuntimeError(f"Smoke test root must not exist: {test_root}")
    test_root.parent.mkdir(parents=True, exist_ok=True)
    test_root.mkdir()
    (test_root / ".baw_smoke_test").write_text("isolated-factory-test", encoding="utf-8")

    for obj in tuple(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for collection in tuple(bpy.data.collections):
        bpy.data.collections.remove(collection)
    for action in tuple(bpy.data.actions):
        bpy.data.actions.remove(action)

    scene = bpy.context.scene
    settings = scene.baw_settings
    settings.project_root = test_root.anchor
    expect_value_error(
        lambda: module.utils.validate_project_root(Path(test_root.anchor)),
        "Drive root utility safety check failed",
        "盘符根目录",
    )
    expect_cancelled(bpy.ops.baw.setup_project, "Drive root safety check failed", "盘符根目录")
    settings.project_root = str(test_root)

    check(bpy.ops.baw.setup_project() == {"FINISHED"}, "Project setup failed")
    check((test_root / ".baw_workspace").is_file(), "Workspace marker missing")
    check((test_root / "50_cache" / "baw_generated").is_dir(), "Generated cache missing")
    check((test_root / "50_cache" / "baw_generated" / ".baw_cache_owner").is_file(), "Cache owner marker missing")

    unknown_root = test_root / "unknown_marker_project"
    unknown_root.mkdir()
    unknown_marker = unknown_root / ".baw_workspace"
    unknown_marker.write_text("user-owned marker", encoding="utf-8")
    settings.project_root = str(unknown_root)
    expect_value_error(
        lambda: module.utils.create_project_folders(unknown_root),
        "Unknown marker utility check failed",
        "所有权标记",
    )
    expect_cancelled(bpy.ops.baw.setup_project, "Unknown marker should not be overwritten", "所有权标记")
    check(unknown_marker.read_text(encoding="utf-8") == "user-owned marker", "Unknown marker changed")
    settings.project_root = str(test_root)

    legacy_root = test_root / "legacy_0_1_0_project"
    legacy_cache = legacy_root / "50_cache" / "baw_generated"
    legacy_cache.mkdir(parents=True)
    legacy_payload = {"tool": "BA Animation Workflow", "version": "0.1.0"}
    (legacy_root / ".baw_workspace").write_text(json.dumps(legacy_payload), encoding="utf-8")
    legacy_file = legacy_cache / "legacy_cache.bin"
    legacy_file.write_bytes(b"legacy")
    settings.project_root = str(legacy_root)
    check(bpy.ops.baw.setup_project() == {"FINISHED"}, "Legacy project migration failed")
    migrated_payload = json.loads((legacy_root / ".baw_workspace").read_text(encoding="utf-8"))
    check(migrated_payload.get("migrated_from") == "0.1.0", "Legacy project migration was not recorded")
    check(legacy_file.is_file(), "Legacy cache content was removed")
    check((legacy_cache / ".baw_cache_owner").is_file(), "Legacy cache did not receive an owner marker")
    settings.project_root = str(test_root)

    foreign_root = bpy.data.collections.new("BAW_PIPELINE")
    foreign_root["user_owned"] = True
    scene.collection.children.link(foreign_root)
    foreign_world = bpy.data.worlds.new("BAW_World")
    foreign_world.use_nodes = True
    foreign_background = foreign_world.node_tree.nodes.get("Background")
    foreign_background.inputs["Strength"].default_value = 0.73
    scene.world = foreign_world
    foreign_light_data = bpy.data.lights.new("BAW_Key", type="POINT")
    foreign_light_data.energy = 17.0
    foreign_light_object = bpy.data.objects.new("BAW_Key", foreign_light_data)
    foreign_camera_data = bpy.data.cameras.new("BAW_Camera")
    foreign_camera_data.lens = 12.0
    foreign_camera_object = bpy.data.objects.new("BAW_Camera", foreign_camera_data)

    scene.render.fps = 24
    scene.frame_start = 10
    scene.frame_end = 90

    check(bpy.ops.baw.setup_scene() == {"FINISHED"}, "Scene setup failed")
    check(bpy.ops.baw.setup_scene() == {"FINISHED"}, "Idempotent scene setup failed")
    collections = module.operators.ensure_scene_collections()
    check(collections["BAW_PIPELINE"] != foreign_root, "Foreign root collection was hijacked")
    check(foreign_root.get("user_owned") is True, "Foreign root collection changed")
    check((scene.render.fps, scene.frame_start, scene.frame_end) == (24, 10, 90), "Scene setup changed timeline")
    original_scene_id = scene.get("baw_scene_id")
    second_scene = scene.copy()
    second_scene.name = "BAW_SecondSceneCopy"
    second_collections = module.operators.ensure_scene_collections(second_scene)
    check(second_collections["BAW_PIPELINE"] != collections["BAW_PIPELINE"], "Collections leaked across scenes")
    check(second_scene.get("baw_scene_id") != original_scene_id, "Copied Scene kept the original UUID")
    check(collections["BAW_PIPELINE"].name not in second_scene.collection.children, "Copied Scene retained the original root")
    bpy.data.scenes.remove(second_scene)
    scene.frame_start = 1
    scene.frame_end = 120

    armature_data = bpy.data.armatures.new("SmokeArmatureData")
    armature = bpy.data.objects.new("SmokeArmature", armature_data)
    collections["BAW_10_CHARACTER"].objects.link(armature)

    material = bpy.data.materials.new("SmokeAnimeMaterial")
    material.diffuse_color = (0.18, 0.5, 0.95, 1.0)
    material.use_nodes = True
    principled = material.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = (0.08, 0.35, 0.95, 1.0)
    principled.inputs["Roughness"].default_value = 0.48

    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, location=(0.0, 0.0, 1.65), scale=(0.38, 0.32, 0.38))
    head = bpy.context.object
    head.name = "SmokeHead"
    head.data.materials.append(material)
    head.parent = armature
    collections["BAW_10_CHARACTER"].objects.link(head)

    bpy.ops.mesh.primitive_cube_add(location=(0.0, 0.0, 0.82), scale=(0.32, 0.20, 0.62))
    body = bpy.context.object
    body.name = "SmokeBody"
    body.data.materials.append(material)
    body.parent = armature
    collections["BAW_10_CHARACTER"].objects.link(body)

    bpy.context.view_layer.objects.active = armature
    armature.select_set(True)

    for frame in range(1, 62):
        jitter = 0.008 if frame % 2 else -0.008
        armature.location.x = frame * 0.02 + jitter
        armature.location.z = 1.0
        armature.keyframe_insert(data_path="location", index=0, frame=frame)
        armature.keyframe_insert(data_path="location", index=2, frame=frame)

    armature.rotation_mode = "QUATERNION"
    for frame, angle in ((1, 0.0), (31, 0.5), (61, 1.0)):
        armature.rotation_quaternion = Quaternion((0.0, 0.0, 1.0), angle)
        armature.keyframe_insert(data_path="rotation_quaternion", frame=frame)
    armature.rotation_mode = "XYZ"
    for frame, angle_degrees in ((1, 179.0), (31, -179.0), (61, 179.0)):
        armature.rotation_euler.z = math.radians(angle_degrees)
        armature.keyframe_insert(data_path="rotation_euler", index=2, frame=frame)

    raw_action = armature.animation_data.action
    raw_action.name = "ACT_Smoke_RAW"
    raw_keys = key_count(raw_action)
    check(raw_keys == 137, f"Unexpected raw key count: {raw_keys}")
    raw_quaternion = {
        (curve.array_index, point.co.x): point.co.y
        for curve in module.operators.iter_action_fcurves(raw_action)
        if curve.data_path.endswith("rotation_quaternion")
        for point in curve.keyframe_points
    }

    settings.smooth_strength = 0.5
    settings.smooth_passes = 1
    settings.simplify_tolerance = 0.02
    check(bpy.ops.baw.clean_mocap_action() == {"FINISHED"}, "Motion cleanup failed")
    clean_action = armature.animation_data.action
    clean_keys = key_count(clean_action)
    check(clean_action != raw_action, "Cleanup overwrote the raw action")
    check(raw_action.use_fake_user, "Raw action is not protected by Fake User")
    check(key_count(raw_action) == raw_keys, "Raw action keyframes changed")
    check(clean_keys < raw_keys, f"Curve simplification ineffective: {raw_keys} -> {clean_keys}")
    clean_quaternion = {
        (curve.array_index, point.co.x): point.co.y
        for curve in module.operators.iter_action_fcurves(clean_action)
        if curve.data_path.endswith("rotation_quaternion")
        for point in curve.keyframe_points
    }
    check(clean_quaternion == raw_quaternion, "Quaternion curves were modified")
    clean_euler_curve = next(
        curve
        for curve in module.operators.iter_action_fcurves(clean_action)
        if curve.data_path.endswith("rotation_euler") and curve.array_index == 2
    )
    wrapped_error = abs((clean_euler_curve.evaluate(31.0) - math.pi + math.pi) % math.tau - math.pi)
    check(wrapped_error < math.radians(5.0), f"Euler unwrap error too large: {math.degrees(wrapped_error):.2f} deg")

    scene.frame_set(61)
    held_end_x = armature.location.x

    check(bpy.ops.baw.create_correction_layer() == {"FINISHED"}, "Correction layer creation failed")
    correction_action = armature.animation_data.action
    check(correction_action != clean_action, "Correction layer did not create a new action")
    check(correction_action.get("baw_role") == "CORRECTION", "Correction action role missing")
    base_tracks = [track for track in armature.animation_data.nla_tracks if track.name.startswith("BAW_MOCAP_BASE::")]
    check(len(base_tracks) == 1, "Mocap base NLA track missing")
    check(base_tracks[0].strips[0].action == clean_action, "NLA base strip does not use clean action")
    check(base_tracks[0].lock, "Mocap base NLA track is not locked")
    scene.frame_set(31)
    check(abs(armature.location.x - (31 * 0.02 + 0.008)) < 0.05, "Base NLA motion is not evaluating")
    scene.frame_set(62)
    check(abs(armature.location.x - held_end_x) < 1e-5, "Base NLA does not hold after action end")
    scene.frame_set(120)
    check(abs(armature.location.x - held_end_x) < 1e-5, "Base NLA does not hold at scene end")

    settings.shot_type = "MEDIUM"
    settings.light_power = 300.0
    check(bpy.ops.baw.create_light_rig() == {"FINISHED"}, "Light rig creation failed")
    check(bpy.ops.baw.create_light_rig() == {"FINISHED"}, "Idempotent light rig creation failed")
    check(bpy.ops.baw.create_camera_rig() == {"FINISHED"}, "Camera rig creation failed")
    check(bpy.ops.baw.create_camera_rig() == {"FINISHED"}, "Idempotent camera rig creation failed")
    check(scene.camera is not None, "Active camera missing")
    check(sum(1 for obj in scene.objects if obj.type == "LIGHT") == 3, "Expected exactly three lights")
    check(scene.world == foreign_world, "User World was replaced")
    check(abs(foreign_background.inputs["Strength"].default_value - 0.73) < 1e-6, "User World changed")
    check(len(foreign_light_object.users_collection) == 0, "Foreign light object was linked")
    check(foreign_light_data.type == "POINT" and foreign_light_data.energy == 17.0, "Foreign light data changed")
    check(len(foreign_camera_object.users_collection) == 0, "Foreign camera object was linked")
    check(abs(foreign_camera_data.lens - 12.0) < 1e-6, "Foreign camera data changed")
    owned_camera = module.utils.find_owned_object("BAW_Camera", collections["BAW_60_CAMERAS"], "CAMERA")
    check(scene.camera == owned_camera, "Owned camera is not active")

    if module.operators.operator_available(bpy.ops.object.build_camera_rig):
        camera_count = sum(1 for obj in scene.objects if obj.type == "CAMERA")
        settings.camera_rig_mode = "DOLLY"
        check(bpy.ops.baw.create_pro_camera_rig() == {"FINISHED"}, "Add Camera Rigs integration failed")
        check(sum(1 for obj in scene.objects if obj.type == "CAMERA") == camera_count + 1, "Professional rig camera missing")
        scene.camera = owned_camera

    scene.frame_current = 15
    check(bpy.ops.baw.add_camera_cut() == {"FINISHED"}, "Camera marker creation failed")
    markers = [marker for marker in scene.timeline_markers if marker.frame == 15]
    check(markers and markers[0].camera == scene.camera, "Camera marker binding failed")

    check(bpy.ops.baw.prepare_preview() == {"FINISHED"}, "Preview settings failed")
    check(scene.render.engine == "BLENDER_EEVEE", "Unexpected render engine")
    check(scene.render.image_settings.media_type == "VIDEO", "Preview media type is not VIDEO")
    check(scene.render.image_settings.file_format == "FFMPEG", "Preview format is not FFMPEG")

    bpy.context.view_layer.objects.active = armature
    armature.select_set(True)
    check(bpy.ops.baw.audit() == {"FINISHED"}, "Audit failed")
    audit_text = bpy.data.texts.get("BAW_检查报告")
    check(audit_text is not None, "Audit text block missing")
    audit = json.loads(audit_text.as_string())
    check(audit["armature"] == armature.name, "Audit did not find active armature")
    check(audit["camera"] == scene.camera.name, "Audit did not find active camera")

    cache_file = test_root / "50_cache" / "baw_generated" / "delete_me.tmp"
    cache_file.write_text("generated smoke data", encoding="utf-8")
    cache_marker = cache_file.parent / ".baw_cache_owner"
    valid_cache_marker = cache_marker.read_text(encoding="utf-8")
    cache_marker.write_text('{"tool_id":"foreign","project_id":"foreign"}', encoding="utf-8")
    check(not module.utils.cache_is_safe(test_root, cache_file.parent), "Mismatched cache marker passed utility check")
    expect_cancelled(
        lambda: bpy.ops.baw.cleanup_cache("EXEC_DEFAULT"),
        "Mismatched cache marker should block cleanup",
        "安全检查失败",
    )
    check(cache_file.exists(), "Blocked cleanup removed a file")
    cache_marker.write_text(valid_cache_marker, encoding="utf-8")
    check(bpy.ops.baw.cleanup_cache("EXEC_DEFAULT") == {"FINISHED"}, "Safe cache cleanup failed")
    check(not cache_file.exists(), "Generated cache file was not removed")
    check(cache_file.parent.is_dir(), "Generated cache directory was not recreated")
    check(cache_marker.is_file(), "Cache owner marker was not recreated")

    scene.render.image_settings.media_type = "IMAGE"
    scene.render.image_settings.file_format = "PNG"
    scene.render.resolution_x = 320
    scene.render.resolution_y = 180
    scene.render.resolution_percentage = 100
    rendered = []
    for frame in (1, 31, 61):
        scene.frame_set(frame)
        output = test_root / "60_renders_preview" / f"smoke_{frame:04d}.png"
        scene.render.filepath = str(output)
        bpy.ops.render.render(write_still=True)
        check(output.is_file() and output.stat().st_size > 0, f"Render failed at frame {frame}")
        rendered.append(str(output))

    blend_path = test_root / "90_exports" / "BAW_smoke_scene.blend"
    bpy.context.preferences.filepaths.file_preview_type = "NONE"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), check_existing=False)
    check(blend_path.is_file(), "Smoke blend file was not saved")
    foreign_world_name = foreign_world.name
    bpy.ops.wm.open_mainfile(filepath=str(blend_path), load_ui=False)
    scene = bpy.context.scene
    check(scene.world is not None and scene.world.name == foreign_world_name, "User World was lost after reopen")
    reopened_background = scene.world.node_tree.nodes.get("Background")
    check(
        reopened_background is not None
        and abs(reopened_background.inputs["Strength"].default_value - 0.73) < 1e-6,
        "User World changed after reopen",
    )

    result = {
        "status": "PASS",
        "blender": bpy.app.version_string,
        "addon_module": addon_module,
        "raw_keys": raw_keys,
        "clean_keys": clean_keys,
        "quaternion_curves_preserved": True,
        "euler_wrap_preserved": True,
        "foreign_data_preserved": True,
        "user_world_reopen_preserved": True,
        "scene_copy_isolated": True,
        "cache_uuid_guarded": True,
        "lights": [obj.name for obj in scene.objects if obj.type == "LIGHT"],
        "camera": scene.camera.name,
        "rendered_frames": rendered,
        "blend_file": str(blend_path),
    }
    report_path = test_root / "90_exports" / "smoke_report.json"
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("BAW_SMOKE_RESULT=" + json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
