from __future__ import annotations

import importlib
import json
import math
import os
from pathlib import Path
import sys

import bpy
from mathutils import Quaternion


if not bpy.app.background:
    raise RuntimeError("Native toe test refuses to run in Blender UI")
if os.environ.get("BAM_NATIVE_TEST_ALLOW") != "isolated-factory-test":
    raise RuntimeError("Set BAM_NATIVE_TEST_ALLOW=isolated-factory-test explicitly")

WORKSPACE = Path(r"D:\Agent Workspaces\Agent Tools\BA_Animation_Workflow")
sys.path.insert(0, os.environ.get("BAM_BRIDGE_IMPORT_ROOT", str(WORKSPACE / "extension")))
module_name = os.environ.get("BAM_BRIDGE_MODULE", "ba_motion_bridge")
operators = importlib.import_module(module_name + ".operators")
mapping = importlib.import_module(module_name + ".mapping")
native = importlib.import_module(module_name + ".retarget")


def check(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def make_rig(name: str, tail) -> bpy.types.Object:
    data = bpy.data.armatures.new(name + "Data")
    rig = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    toe = data.edit_bones.new("Toe")
    toe.head = (0.0, 0.0, 0.0)
    toe.tail = tail
    bpy.ops.object.mode_set(mode="OBJECT")
    rig.pose.bones["Toe"].rotation_mode = "QUATERNION"
    rig.select_set(False)
    return rig


source = make_rig("SomaSource", (0.0, 0.0, 1.0))
target = make_rig("MmdTarget", (0.0, 1.0, 0.0))
source.animation_data_create()
source_toe = source.pose.bones["Toe"]

bpy.context.scene.frame_set(1)
source_toe.rotation_quaternion = Quaternion()
source_toe.keyframe_insert("rotation_quaternion", frame=1, group="Toe")
bpy.context.scene.frame_set(2)
source_toe.rotation_quaternion = Quaternion((1.0, 0.0, 0.0), math.radians(20.0))
source_toe.keyframe_insert("rotation_quaternion", frame=2, group="Toe")

result = mapping.MappingResult(
    pairs=(mapping.MappingPair("Toe", "Toe", role="left_toe"),),
    missing=(),
    critical_missing=(),
    warnings=(),
    expected_count=1,
)
override = operators._build_source_rest_override(source, target, result)
source_rest_q = source.data.bones["Toe"].matrix_local.to_quaternion()
check(
    override["Toe"].to_quaternion().rotation_difference(source_rest_q).angle < 1e-6,
    "ToeBase was incorrectly forced into target's forward rest direction",
)

progress_events = []
bake = native.bake_retarget(
    bpy.context.scene,
    source,
    target,
    result,
    source_rest_override=override,
    location_scale=1.0,
    world_location=True,
    progress=lambda factor, message: progress_events.append((factor, message)),
)
check(bake.action is target.animation_data.action, "native output Action was not bound")
check(progress_events, "native bake emitted no progress")
check(progress_events[-1][0] == 1.0, "native bake progress did not reach 100%")
check(
    all(left[0] <= right[0] for left, right in zip(progress_events, progress_events[1:])),
    "native bake progress moved backwards",
)
check(not hasattr(bpy.types.Scene, "blendcap_retarget_pairs"), "factory test unexpectedly loaded BlendCap")

bpy.context.scene.frame_set(1)
bpy.context.view_layer.update()
neutral_angle = target.pose.bones["Toe"].matrix_basis.to_quaternion().angle
check(neutral_angle < math.radians(0.01), f"MMD toe lifted at neutral frame: {math.degrees(neutral_angle)}")

bpy.context.scene.frame_set(2)
bpy.context.view_layer.update()
motion_angle = target.pose.bones["Toe"].matrix_basis.to_quaternion().angle
check(abs(motion_angle - math.radians(20.0)) < math.radians(0.1), "toe motion delta was not preserved")

print(
    "PMB_NATIVE_TOE_TEST="
    + json.dumps(
        {
            "status": "PASS",
            "engine": "native",
            "blendcap_loaded": False,
            "neutral_degrees": math.degrees(neutral_angle),
            "motion_degrees": math.degrees(motion_angle),
            "frames": [bake.frame_start, bake.frame_end],
            "progress_events": len(progress_events),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
)
