from __future__ import annotations

import importlib
import json
import math
import os
from pathlib import Path
import re
import sys

import bpy


if not bpy.app.background:
    raise RuntimeError("ARP pose regression refuses to run in Blender UI")
if os.environ.get("BAM_REAL_TEST_ALLOW") != "isolated-fixture-copy":
    raise RuntimeError("Set BAM_REAL_TEST_ALLOW=isolated-fixture-copy explicitly")
fixture_path = Path(bpy.data.filepath).resolve()
if "motion-bridge-arm-regression" not in {part.lower() for part in fixture_path.parts}:
    raise RuntimeError(f"Refusing non-fixture .blend: {fixture_path}")


WORKSPACE = Path(r"D:\Agent Workspaces\Agent Tools\BA_Animation_Workflow")
sys.path.insert(0, str(WORKSPACE / "extension"))
module_name = os.environ.get("BAM_BRIDGE_MODULE", "ba_motion_bridge")
bridge = importlib.import_module(module_name)
bridge_ops = importlib.import_module(module_name + ".operators")
build_mapping = importlib.import_module(module_name + ".mapping").build_mapping


def check(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def pose_head(rig, bone_name):
    return rig.matrix_world @ rig.pose.bones[bone_name].matrix.translation


def chain_direction(rig, root_name, end_name):
    direction = pose_head(rig, end_name) - pose_head(rig, root_name)
    check(direction.length > 1e-8, f"zero-length pose chain: {root_name} -> {end_name}")
    return direction.normalized()


def direction_error_degrees(a, b) -> float:
    return math.degrees(a.angle(b))


def action_bone_names(action) -> set[str]:
    result = set()
    for fcurve in bridge_ops._iter_action_fcurves(action):
        match = re.match(r'^pose\.bones\["(.+?)"\]', fcurve.data_path)
        if match:
            result.add(match.group(1))
    return result


for installed in (
    "bl_ext.user_default.ba_motion_bridge",
    "bl_ext.user_default.proscenium_motion_bridge",
):
    if installed in bpy.context.preferences.addons:
        disabled = bpy.ops.preferences.addon_disable(module=installed)
        check(disabled == {"FINISHED"}, f"could not disable installed bridge: {installed}")

if not hasattr(bpy.types.Scene, "ba_motion_bridge_settings"):
    bridge.register()

scene = bpy.context.scene
source = bpy.data.objects.get("kimodo-soma-rp")
target = bpy.data.objects.get("rig")
check(source is not None and source.type == "ARMATURE", "canonical source missing")
check(target is not None and target.type == "ARMATURE", "ARP target missing")
check(not hasattr(bpy.types.Scene, "blendcap_retarget_pairs"), "fixture unexpectedly loaded BlendCap")

mapping = build_mapping(source, target, "FULL")
check(mapping.target_profile == "AUTO_RIG_PRO", "real ARP profile was not detected")
check(mapping.matched_count == 24 and not mapping.critical_missing, "real ARP main chain incomplete")
mapped_targets = {pair.target for pair in mapping.pairs}
check("c_arm_fk.l" in mapped_targets and "c_arm_fk.r" in mapped_targets, "ARP FK arm controls missing")
check("arm.l" not in mapped_targets and "arm.r" not in mapped_targets, "ARP mechanism bones selected")

original_action = target.animation_data.action if target.animation_data else None
switch_rows = bridge_ops._target_switch_snapshot(target)
check(switch_rows and all(abs(row["value"]) < 1e-6 for row in switch_rows), "fixture did not start in IK")

settings = scene.ba_motion_bridge_settings
settings.source_rig = source
settings.target_rig = target
settings.root_motion_mode = "FULL"
settings.auto_scale = True
settings.world_location = True

result = bpy.ops.ba_motion_bridge.retarget("EXEC_DEFAULT")
check(result == {"FINISHED"}, f"ARP retarget failed: {result}")
output_action = target.animation_data.action
check(output_action is not None and output_action != original_action, "independent ARP output missing")
check(output_action.get("bam_target_profile") == "AUTO_RIG_PRO", "output profile tag missing")

keyed_bones = action_bone_names(output_action)
check("c_arm_fk.l" in keyed_bones and "c_forearm_fk.l" in keyed_bones, "left ARP controls not keyed")
check("c_arm_fk.r" in keyed_bones and "c_forearm_fk.r" in keyed_bones, "right ARP controls not keyed")
check("arm.l" not in keyed_bones and "forearm.l" not in keyed_bones, "constrained left mechanism bones keyed")
check("arm.r" not in keyed_bones and "forearm.r" not in keyed_bones, "constrained right mechanism bones keyed")

scene.frame_set(1)
bpy.context.view_layer.update()
errors = {}
for side, source_prefix, target_suffix in (
    ("left", "Left", "l"),
    ("right", "Right", "r"),
):
    source_upper = chain_direction(source, source_prefix + "Arm", source_prefix + "ForeArm")
    target_upper = chain_direction(target, f"arm.{target_suffix}", f"forearm.{target_suffix}")
    source_full = chain_direction(source, source_prefix + "Arm", source_prefix + "Hand")
    target_full = chain_direction(target, f"arm.{target_suffix}", f"hand.{target_suffix}")
    errors[side + "_upper"] = direction_error_degrees(source_upper, target_upper)
    errors[side + "_full"] = direction_error_degrees(source_full, target_full)

check(max(errors.values()) < 8.0, f"arm-chain direction error too large: {errors}")
current_switches = bridge_ops._target_switch_snapshot(target)
check(current_switches and all(abs(row["value"] - 1.0) < 1e-6 for row in current_switches), "ARP output did not stay in FK")

restored = bpy.ops.ba_motion_bridge.restore_previous_state("EXEC_DEFAULT")
check(restored == {"FINISHED"}, f"ARP state restore failed: {restored}")
check(target.animation_data.action == original_action, "ARP original action was not restored")
restored_switches = bridge_ops._target_switch_snapshot(target)
check(restored_switches == switch_rows, "ARP IK/FK properties were not restored exactly")

report = {
    "status": "PASS",
    "source": source.name,
    "target": target.name,
    "profile": mapping.target_profile,
    "pairs": mapping.matched_count,
    "output_action": output_action.name,
    "keyed_controls": sorted(name for name in keyed_bones if name.startswith("c_") and "arm" in name or "forearm" in name),
    "direction_error_degrees": errors,
    "fk_switch_during_output": 1.0,
    "switch_state_restored": True,
}
print("PMB_ARP_POSE_REGRESSION=" + json.dumps(report, ensure_ascii=False))
