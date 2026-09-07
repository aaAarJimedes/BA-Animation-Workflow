from __future__ import annotations

import json
import importlib
import os
from pathlib import Path
import sys

import bpy
from mathutils import Quaternion, Vector


if not bpy.app.background:
    raise RuntimeError("Motion Bridge mapping test refuses to run in Blender UI")
if os.environ.get("BAM_MAPPING_TEST_ALLOW") != "isolated-factory-test":
    raise RuntimeError("Set BAM_MAPPING_TEST_ALLOW=isolated-factory-test explicitly")


WORKSPACE = Path(r"D:\Agent Workspaces\Agent Tools\BA_Animation_Workflow")
sys.path.insert(0, os.environ.get("BAM_BRIDGE_IMPORT_ROOT", str(WORKSPACE / "extension")))

bridge_module_name = os.environ.get("BAM_BRIDGE_MODULE", "ba_motion_bridge")
workflow_module_name = os.environ.get("BAM_WORKFLOW_MODULE", "ba_animation_workflow")
ba_motion_bridge = importlib.import_module(bridge_module_name)
ba_animation_workflow = importlib.import_module(workflow_module_name)
build_mapping = importlib.import_module(bridge_module_name + ".mapping").build_mapping
bridge_operators = importlib.import_module(bridge_module_name + ".operators")
native_retarget = importlib.import_module(bridge_module_name + ".retarget")


def check(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def create_armature(name: str, specs: list[tuple[str, str | None, tuple[float, float, float], tuple[float, float, float]]]):
    data = bpy.data.armatures.new(name + "Data")
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bones = {}
    for bone_name, parent_name, head, tail in specs:
        bone = data.edit_bones.new(bone_name)
        bone.head = head
        bone.tail = tail
        bone.parent = bones.get(parent_name)
        bones[bone_name] = bone
    bpy.ops.object.mode_set(mode="OBJECT")
    obj.select_set(False)
    return obj


source_specs = [
    ("Hips", None, (0, 0, 1.0), (0, 0, 1.1)),
    ("Spine1", "Hips", (0, 0, 1.1), (0, 0, 1.2)),
    ("Spine2", "Spine1", (0, 0, 1.2), (0, 0, 1.35)),
    ("Chest", "Spine2", (0, 0, 1.35), (0, 0, 1.5)),
    ("Neck1", "Chest", (0, 0, 1.5), (0, 0, 1.56)),
    ("Neck2", "Neck1", (0, 0, 1.56), (0, 0, 1.62)),
    ("Head", "Neck2", (0, 0, 1.62), (0, 0, 1.75)),
]
for side, sign in (("Left", 1.0), ("Right", -1.0)):
    source_specs.extend(
        [
            (side + "Shoulder", "Chest", (0, 0, 1.45), (0.15 * sign, 0, 1.45)),
            (side + "Arm", side + "Shoulder", (0.15 * sign, 0, 1.45), (0.45 * sign, 0, 1.45)),
            (side + "ForeArm", side + "Arm", (0.45 * sign, 0, 1.45), (0.72 * sign, 0, 1.45)),
            (side + "Hand", side + "ForeArm", (0.72 * sign, 0, 1.45), (0.84 * sign, 0, 1.45)),
            (side + "Leg", "Hips", (0.1 * sign, 0, 0.95), (0.1 * sign, 0, 0.5)),
            (side + "Shin", side + "Leg", (0.1 * sign, 0, 0.5), (0.1 * sign, 0, 0.1)),
            (side + "Foot", side + "Shin", (0.1 * sign, 0, 0.1), (0.1 * sign, -0.15, 0.03)),
            (side + "ToeBase", side + "Foot", (0.1 * sign, -0.15, 0.03), (0.1 * sign, -0.25, 0.03)),
        ]
    )
source_specs.extend(
    [
        ("Jaw", "Head", (0, -0.04, 1.66), (0, -0.08, 1.62)),
        ("LeftEye", "Head", (0.03, -0.05, 1.69), (0.03, -0.08, 1.69)),
        ("RightEye", "Head", (-0.03, -0.05, 1.69), (-0.03, -0.08, 1.69)),
        ("LeftHandThumbEnd", "LeftHand", (0.84, 0, 1.45), (0.9, -0.03, 1.43)),
        ("LeftHandMiddleEnd", "LeftHand", (0.84, 0, 1.45), (0.94, 0, 1.45)),
        ("RightHandThumbEnd", "RightHand", (-0.84, 0, 1.45), (-0.9, -0.03, 1.43)),
        ("RightHandMiddleEnd", "RightHand", (-0.84, 0, 1.45), (-0.94, 0, 1.45)),
    ]
)

target_specs = [
    ("全ての親", None, (0, 0, 0), (0, 0, 0.1)),
    ("センター", "全ての親", (0, 0, 0.8), (0, 0, 0.9)),
    ("グルーブ", "センター", (0, 0, 0.85), (0, 0, 0.95)),
    ("腰", "グルーブ", (0, 0, 0.95), (0, 0, 1.03)),
    ("下半身", "腰", (0, 0, 1.03), (0, 0, 1.15)),
    ("上半身", "下半身", (0, 0, 1.15), (0, 0, 1.35)),
    ("上半身2", "上半身", (0, 0, 1.35), (0, 0, 1.5)),
    ("首", "上半身2", (0, 0, 1.5), (0, 0, 1.58)),
    ("頭", "首", (0, 0, 1.58), (0, 0, 1.72)),
]
for jp, suffix, sign in (("左", ".L", 1.0), ("右", ".R", -1.0)):
    target_specs.extend(
        [
            ("肩" + suffix, "上半身2", (0, 0, 1.46), (0.14 * sign, 0, 1.42)),
            ("腕" + suffix, "肩" + suffix, (0.14 * sign, 0, 1.42), (0.42 * sign, 0, 1.35)),
            ("ひじ" + suffix, "腕" + suffix, (0.42 * sign, 0, 1.35), (0.68 * sign, 0, 1.30)),
            ("手首" + suffix, "ひじ" + suffix, (0.68 * sign, 0, 1.30), (0.8 * sign, 0, 1.28)),
            ("足" + suffix, "腰", (0.09 * sign, 0, 0.93), (0.09 * sign, 0.02, 0.48)),
            ("ひざ" + suffix, "足" + suffix, (0.09 * sign, 0.02, 0.48), (0.09 * sign, 0.04, 0.08)),
            ("足首" + suffix, "ひざ" + suffix, (0.09 * sign, 0.04, 0.08), (0.09 * sign, -0.13, 0.02)),
            ("つま先" + suffix, "足首" + suffix, (0.09 * sign, -0.13, 0.02), (0.09 * sign, -0.24, 0.02)),
        ]
    )

source = create_armature("kimodo-soma-rp", source_specs)
source["proscenium_canonical_model"] = "kimodo-soma-rp"
target = create_armature("SyntheticMMD", target_specs)

result = build_mapping(source, target, "FULL")
check(result.matched_count == 24, f"expected 24 pairs, got {result.matched_count}")
check(not result.critical_missing, f"unexpected critical gaps: {result.critical_missing}")
check(len({(p.target, p.channels, p.axes) for p in result.pairs}) == 24, "duplicate output pairs")
check(any(p.source == "LeftLeg" and p.target == "足.L" for p in result.pairs), "left thigh mapping wrong")
check(not any(p.source == "LeftLeg" and p.target == "ひざ.L" for p in result.pairs), "SOMA thigh mapped to knee")

# Exercise the entire native 24-pair bake without loading BlendCap.  The
# direction-aligned arm path should reproduce the source's posed world
# direction instead of adding the MMD A-pose rest angle a second time.
source.animation_data_create()
for bone in source.pose.bones:
    bone.rotation_mode = "QUATERNION"
bpy.context.scene.frame_set(1)
source.pose.bones["LeftArm"].rotation_quaternion = Quaternion()
source.pose.bones["LeftArm"].keyframe_insert("rotation_quaternion", frame=1, group="LeftArm")
bpy.context.scene.frame_set(2)
source.pose.bones["LeftArm"].rotation_quaternion = Quaternion((0.0, 1.0, 0.0), 0.35)
source.pose.bones["LeftArm"].keyframe_insert("rotation_quaternion", frame=2, group="LeftArm")
native_bake = native_retarget.bake_retarget(
    bpy.context.scene,
    source,
    target,
    result,
    source_rest_override=bridge_operators._build_source_rest_override(source, target, result),
    location_scale=1.0,
    world_location=True,
)
check(native_bake.action is target.animation_data.action, "native full-chain Action was not bound")
check(native_bake.keyed_channels > 0, "native full-chain bake inserted no keys")
check(not hasattr(bpy.types.Scene, "blendcap_retarget_pairs"), "native bake loaded BlendCap state")
bpy.context.scene.frame_set(2)
bpy.context.view_layer.update()
source_arm_world = (source.matrix_world @ source.pose.bones["LeftArm"].matrix).to_quaternion()
target_arm_world = (target.matrix_world @ target.pose.bones["腕.L"].matrix).to_quaternion()
source_arm_direction = source_arm_world @ Vector((0.0, 1.0, 0.0))
target_arm_direction = target_arm_world @ Vector((0.0, 1.0, 0.0))
arm_direction_error = source_arm_direction.angle(target_arm_direction)
check(
    arm_direction_error < 1e-4,
    f"native arm direction compensation error: {arm_direction_error}",
)

# Run the public output operator once so the staged WindowManager progress
# lifecycle, transaction wrapper and native engine are covered together.
ba_motion_bridge.register()
bridge_settings = bpy.context.scene.ba_motion_bridge_settings
bridge_settings.source_rig = source
bridge_settings.target_rig = target
bridge_settings.root_motion_policy = "FULL"
bridge_settings.auto_scale = False
bridge_settings.world_location = True
bridge_settings.use_start_buffer = False
operator_result = bpy.ops.ba_motion_bridge.retarget("EXEC_DEFAULT")
check(operator_result == {"FINISHED"}, f"native operator retarget failed: {operator_result}")
operator_action = target.animation_data.action
check(operator_action.get("bam_engine") == "Proscenium Motion Bridge Native", "native engine tag missing")
check(not bridge_settings.progress_active, "retarget left progress UI stuck")
restore_result = bpy.ops.ba_motion_bridge.restore_previous_state("EXEC_DEFAULT")
check(restore_result == {"FINISHED"}, f"operator state restore failed: {restore_result}")
real_bake = bridge_operators.bake_retarget


def injected_bake_failure(*_args, **_kwargs):
    raise RuntimeError("injected progress rollback failure")


bridge_operators.bake_retarget = injected_bake_failure
try:
    try:
        failure_result = bpy.ops.ba_motion_bridge.retarget("EXEC_DEFAULT")
    except RuntimeError as exc:
        check("injected progress rollback failure" in str(exc), f"unexpected injected error: {exc}")
        failure_result = {"CANCELLED"}
finally:
    bridge_operators.bake_retarget = real_bake
check(failure_result == {"CANCELLED"}, f"injected retarget failure unexpectedly succeeded: {failure_result}")
check(not bridge_settings.progress_active, "failed retarget left progress UI stuck")
ba_motion_bridge.unregister()

in_place = build_mapping(source, target, "IN_PLACE")
check(in_place.matched_count == 22 and in_place.expected_count == 22, "in-place mapping count wrong")
check(not any(p.channels == "LOC" for p in in_place.pairs), "in-place mode contains root location")

# MMD characters converted to Auto-Rig Pro expose tempting mechanism bones
# such as arm.l/forearm.l/hand.l.  Those are constraint outputs and must not
# receive retarget keys.  The Bridge must select BlendCap's verified c_* FK
# controls and the dedicated root-motion controls instead.
arp_specs = [
    ("c_pos", None, (0, 0, 0), (0, 0, 0.1)),
    ("c_root_master.x", "c_pos", (0, 0, 0.9), (0, 0, 1.0)),
    ("c_root.x", "c_root_master.x", (0, 0, 1.0), (0, 0, 1.1)),
    ("c_spine_01.x", "c_root.x", (0, 0, 1.1), (0, 0, 1.25)),
    ("c_spine_02.x", "c_spine_01.x", (0, 0, 1.25), (0, 0, 1.4)),
    ("c_spine_03.x", "c_spine_02.x", (0, 0, 1.4), (0, 0, 1.5)),
    ("c_neck.x", "c_spine_03.x", (0, 0, 1.5), (0, 0, 1.6)),
    ("c_head.x", "c_neck.x", (0, 0, 1.6), (0, 0, 1.75)),
]
for side, sign in (("l", 1.0), ("r", -1.0)):
    arp_specs.extend(
        [
            (f"c_shoulder.{side}", "c_spine_03.x", (0, 0, 1.48), (0.15 * sign, 0, 1.48)),
            (f"c_arm_fk.{side}", "c_spine_03.x", (0.15 * sign, 0, 1.48), (0.45 * sign, 0, 1.45)),
            (f"c_forearm_fk.{side}", f"c_arm_fk.{side}", (0.45 * sign, 0, 1.45), (0.72 * sign, 0, 1.42)),
            (f"c_hand_fk.{side}", f"c_forearm_fk.{side}", (0.72 * sign, 0, 1.42), (0.84 * sign, 0, 1.40)),
            (f"c_thigh_fk.{side}", "c_root.x", (0.1 * sign, 0, 1.0), (0.1 * sign, 0, 0.55)),
            (f"c_leg_fk.{side}", f"c_thigh_fk.{side}", (0.1 * sign, 0, 0.55), (0.1 * sign, 0, 0.12)),
            (f"c_foot_fk.{side}", f"c_leg_fk.{side}", (0.1 * sign, 0, 0.12), (0.1 * sign, -0.18, 0.04)),
            (f"c_toes_fk.{side}", f"c_foot_fk.{side}", (0.1 * sign, -0.18, 0.04), (0.1 * sign, -0.28, 0.04)),
            (f"arm.{side}", f"c_shoulder.{side}", (0.15 * sign, 0, 1.48), (0.45 * sign, 0, 1.45)),
            (f"forearm.{side}", f"arm.{side}", (0.45 * sign, 0, 1.45), (0.72 * sign, 0, 1.42)),
            (f"hand.{side}", f"forearm.{side}", (0.72 * sign, 0, 1.42), (0.84 * sign, 0, 1.40)),
        ]
    )
arp_target = create_armature("SyntheticARP", arp_specs)
arp_result = build_mapping(source, arp_target, "FULL")
check(arp_result.target_profile == "AUTO_RIG_PRO", "ARP target profile was not detected")
check(arp_result.matched_count == 24 and not arp_result.critical_missing, "ARP main chain incomplete")
check(
    any(pair.source == "LeftArm" and pair.target == "c_arm_fk.l" for pair in arp_result.pairs),
    "ARP upper arm did not map to FK control",
)
check(
    not any(pair.target in {"arm.l", "forearm.l", "hand.l", "arm.r", "forearm.r", "hand.r"} for pair in arp_result.pairs),
    "ARP mapping selected constrained mechanism/deform bones",
)

bpy.context.view_layer.objects.active = target
target.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
target.data.edit_bones.remove(target.data.edit_bones["ひざ.R"])
bpy.ops.object.mode_set(mode="OBJECT")
missing = build_mapping(source, target, "FULL")
check(any("小腿" in item for item in missing.critical_missing), "missing critical shin was not rejected")

# Both extensions must register without optional dependencies and in either
# order; this guards the unified panel's soft-dependency boundary.
if hasattr(bpy.types.Scene, "ba_motion_bridge_settings"):
    ba_motion_bridge.unregister()
if hasattr(bpy.types.Scene, "baw_settings"):
    ba_animation_workflow.unregister()
ba_animation_workflow.register()
ba_motion_bridge.register()
check(hasattr(bpy.types.Scene, "baw_settings"), "BA Workflow settings missing")
check(hasattr(bpy.types.Scene, "ba_motion_bridge_settings"), "Bridge settings missing")
ba_motion_bridge.unregister()
ba_animation_workflow.unregister()
ba_motion_bridge.register()
ba_animation_workflow.register()

report = {
    "status": "PASS",
    "full_pairs": result.matched_count,
    "in_place_pairs": in_place.matched_count,
    "critical_gate": list(missing.critical_missing),
    "arp_pairs": arp_result.matched_count,
    "arp_profile": arp_result.target_profile,
    "native_keyed_channels": native_bake.keyed_channels,
    "native_arm_error_degrees": arm_direction_error * 57.29577951308232,
    "operator_progress_cleared": True,
    "failure_progress_cleared": True,
    "registration_orders": 2,
}
print("BAM_MAPPING_TEST=" + json.dumps(report, ensure_ascii=False))
