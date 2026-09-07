from __future__ import annotations

import importlib
import json
import math
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import bpy
from mathutils import Quaternion


if not bpy.app.background:
    raise RuntimeError("Start-buffer test refuses to run in Blender UI")
if os.environ.get("BAM_BUFFER_TEST_ALLOW") != "isolated-factory-test":
    raise RuntimeError("Set BAM_BUFFER_TEST_ALLOW=isolated-factory-test explicitly")

WORKSPACE = Path(r"D:\Agent Workspaces\Agent Tools\BA_Animation_Workflow")
sys.path.insert(0, os.environ.get("BAM_BRIDGE_IMPORT_ROOT", str(WORKSPACE / "extension")))
module_name = os.environ.get("BAM_BRIDGE_MODULE", "ba_motion_bridge")
operators = importlib.import_module(module_name + ".operators")
mapping = importlib.import_module(module_name + ".mapping")


def check(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


data = bpy.data.armatures.new("BufferTargetData")
target = bpy.data.objects.new("BufferTarget", data)
bpy.context.scene.collection.objects.link(target)
bpy.context.view_layer.objects.active = target
target.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
body = data.edit_bones.new("body")
body.head = (0.0, 0.0, 0.0)
body.tail = (0.0, 1.0, 0.0)
skirt = data.edit_bones.new("skirt")
skirt.head = (0.0, 0.0, 0.0)
skirt.tail = (0.0, 0.0, -1.0)
bpy.ops.object.mode_set(mode="OBJECT")

pose_body = target.pose.bones["body"]
pose_body.rotation_mode = "QUATERNION"
target.animation_data_create()

scene = bpy.context.scene
scene.frame_set(10)
pose_body.rotation_quaternion = Quaternion((0.0, 0.0, 1.0), math.radians(90.0))
pose_body.keyframe_insert("rotation_quaternion", frame=10, group="body")
scene.frame_set(20)
pose_body.rotation_quaternion = Quaternion((0.0, 0.0, 1.0), math.radians(120.0))
pose_body.keyframe_insert("rotation_quaternion", frame=20, group="body")
action = target.animation_data.action
check(action is not None, "test action was not created")

result = mapping.MappingResult(
    pairs=(mapping.MappingPair("Arm", "body", channels="ROT", role="left_upper_arm"),),
    missing=(),
    critical_missing=(),
    warnings=(),
    expected_count=1,
)
initial_pose = {"body": pose_body.matrix_basis.copy()}
initial_pose["body"].identity()

buffer_progress = []
buffer = operators._insert_start_buffer(
    scene,
    target,
    action,
    result,
    initial_pose,
    settle_frames=2,
    transition_frames=3,
    progress=lambda factor, message: buffer_progress.append((factor, message)),
)
check(buffer_progress and buffer_progress[-1][0] == 1.0, "buffer progress did not reach 100%")
check(buffer["preroll_start"] == 5, f"unexpected preroll start: {buffer}")
check(buffer["motion_start"] == 10, f"formal motion start moved: {buffer}")
check(bool(action.use_frame_range), "custom action range was not enabled")
check(int(action.frame_start) == 10 and int(action.frame_end) == 20, "formal action range not trimmed")

# The pre-roll must be reachable by the timeline and MMD Tools cache, and the
# active frame must be left at that start instead of the first motion pose.
scene.frame_start = 1
scene.frame_set(1)
bpy.ops.mesh.primitive_cube_add()
bpy.ops.rigidbody.object_add()
rigidbody_cache = scene.rigidbody_world.point_cache
rigidbody_cache.frame_start = 1
timeline_before = operators._timeline_snapshot(scene)
cache_before = operators._physics_cache_snapshot(scene)
timeline_result = operators._extend_preroll_timeline(scene, -5)
check(timeline_result["timeline_start"] == -5, f"timeline was not extended: {timeline_result}")
check(scene.frame_start == 0, "Blender 5.1 scene start clamp was not respected")
check(scene.use_preview_range and scene.frame_preview_start == -5, "negative preview range was not exposed")
check(scene.frame_current == -5, "timeline did not stop at negative pre-roll start")
check(rigidbody_cache.frame_start == -5, "MMD rigid-body cache did not extend to negative pre-roll")
check(operators._restore_timeline_snapshot(scene, timeline_before), "timeline snapshot did not restore")
check(operators._restore_physics_cache_snapshot(scene, cache_before), "physics cache snapshot did not restore")
check(scene.frame_start == 1 and scene.frame_current == 1, "timeline restore was not exact")
check(rigidbody_cache.frame_start == 1, "physics cache restore was not exact")

# AUTO is a single policy selector: it follows Proscenium, while explicit
# choices override Proscenium without exposing a second conflicting toggle.
root_settings = SimpleNamespace(root_motion_policy="AUTO", root_motion_mode="FULL")
root_scene = SimpleNamespace(proscenium=SimpleNamespace(inplace=True))
operators._sync_proscenium_inplace(root_scene, root_settings)
check(root_settings.root_motion_mode == "IN_PLACE", "AUTO root motion did not follow Proscenium")
root_settings.root_motion_policy = "FULL"
operators._sync_proscenium_inplace(root_scene, root_settings)
check(root_settings.root_motion_mode == "FULL", "explicit FULL root motion did not override Proscenium")

scene.frame_set(5)
bpy.context.view_layer.update()
start_angle = pose_body.rotation_quaternion.angle
scene.frame_set(6)
bpy.context.view_layer.update()
settle_angle = pose_body.rotation_quaternion.angle
scene.frame_set(8)
bpy.context.view_layer.update()
transition_angle_1 = pose_body.rotation_quaternion.angle
scene.frame_set(9)
bpy.context.view_layer.update()
transition_angle_2 = pose_body.rotation_quaternion.angle
scene.frame_set(10)
bpy.context.view_layer.update()
first_angle = pose_body.rotation_quaternion.angle
check(start_angle < math.radians(0.01), f"initial pose not held: {math.degrees(start_angle)}")
check(settle_angle < math.radians(0.01), f"stable buffer did not hold the initial pose: {math.degrees(settle_angle)}")
check(
    math.radians(0.01) < transition_angle_1 < transition_angle_2 < first_angle,
    "transition frames did not progressively approach the formal first pose",
)
check(abs(first_angle - math.radians(90.0)) < math.radians(0.01), "formal first pose changed")

keyed_bones = set()
for fcurve in operators._iter_action_fcurves(action):
    if 'pose.bones["body"]' in fcurve.data_path:
        keyed_bones.add("body")
    if 'pose.bones["skirt"]' in fcurve.data_path:
        keyed_bones.add("skirt")
check(keyed_bones == {"body"}, f"secondary bones were unexpectedly keyed: {keyed_bones}")

# The user-selectable Action/frame source must be sampled transactionally and
# leave the formal output Action bound afterward.
initial_action = bpy.data.actions.new("UserSelectedInitialPose")
operators._bind_action(target.animation_data, initial_action)
scene.frame_set(3)
pose_body.rotation_quaternion = Quaternion((0.0, 0.0, 1.0), math.radians(30.0))
pose_body.keyframe_insert("rotation_quaternion", frame=3, group="body")
operators._bind_action(target.animation_data, action)
settings = SimpleNamespace(
    initial_pose_source="ACTION_FRAME",
    initial_pose_action=initial_action,
    initial_pose_frame=3,
)
captured = operators._capture_buffer_initial_pose(scene, settings, target, result)
captured_angle = captured["body"].to_quaternion().angle
check(abs(captured_angle - math.radians(30.0)) < math.radians(0.01), "selected Action pose was not sampled")
check(target.animation_data.action == action, "selected Action sampling changed the bound output")

print(
    "PMB_START_BUFFER_TEST="
    + json.dumps(
        {
            "status": "PASS",
            "preroll_start": buffer["preroll_start"],
            "motion_range": [int(action.frame_start), int(action.frame_end)],
            "initial_angle_degrees": math.degrees(start_angle),
            "settle_angle_degrees": math.degrees(settle_angle),
            "transition_angles_degrees": [
                math.degrees(transition_angle_1),
                math.degrees(transition_angle_2),
            ],
            "first_angle_degrees": math.degrees(first_angle),
            "selected_action_angle_degrees": math.degrees(captured_angle),
            "keyed_bones": sorted(keyed_bones),
            "timeline_start": timeline_result["timeline_start"],
            "root_motion_policy": root_settings.root_motion_mode,
        },
        ensure_ascii=False,
    )
)
