from __future__ import annotations

import json
import importlib
import math
import os
from pathlib import Path
import sys

import bpy
from mathutils import Quaternion, Vector


if not bpy.app.background:
    raise RuntimeError("Real retarget smoke refuses to run in Blender UI")
if os.environ.get("BAM_REAL_TEST_ALLOW") != "isolated-fixture-copy":
    raise RuntimeError("Set BAM_REAL_TEST_ALLOW=isolated-fixture-copy explicitly")
fixture_path = Path(bpy.data.filepath).resolve()
if "motion-bridge-real-fixture" not in {part.lower() for part in fixture_path.parts}:
    raise RuntimeError(f"Refusing non-fixture .blend: {fixture_path}")


WORKSPACE = Path(r"D:\Agent Workspaces\Agent Tools\BA_Animation_Workflow")
EXTENSION_ROOT = WORKSPACE / "extension"
CANONICAL_BLEND = WORKSPACE / "smoke_runs" / "proscenium-hosted-0.4.0" / "canonical_skeleton_smoke.blend"

sys.path.insert(0, str(EXTENSION_ROOT))
bridge_module_name = os.environ.get("BAM_BRIDGE_MODULE", "ba_motion_bridge")
ba_motion_bridge = importlib.import_module(bridge_module_name)
bridge_ops = importlib.import_module(bridge_module_name + ".operators")
build_mapping = importlib.import_module(bridge_module_name + ".mapping").build_mapping


def check(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def action_key_count(action) -> int:
    return sum(len(fcurve.keyframe_points) for fcurve in bridge_ops._iter_action_fcurves(action))


def constraint_state(rig) -> dict[str, tuple[bool, float]]:
    return {
        f"{pose_bone.name}\0{constraint.name}": (bool(constraint.mute), float(constraint.influence))
        for pose_bone in rig.pose.bones
        for constraint in pose_bone.constraints
    }


if not hasattr(bpy.types.Scene, "ba_motion_bridge_settings"):
    ba_motion_bridge.register()

scene = bpy.context.scene
source = bpy.data.objects.get("kimodo-soma-rp")
if source is None:
    with bpy.data.libraries.load(str(CANONICAL_BLEND), link=False) as (data_from, data_to):
        data_to.objects = ["kimodo-soma-rp"] if "kimodo-soma-rp" in data_from.objects else []
    source = next(obj for obj in data_to.objects if obj is not None)
    scene.collection.objects.link(source)

target = bpy.data.objects.get("星野（二年级）_arm")
check(target is not None and target.type == "ARMATURE", "real MMD target missing")
check(not hasattr(bpy.types.Scene, "blendcap_retarget_pairs"), "fixture unexpectedly loaded BlendCap")

scene.frame_start = 1
scene.frame_end = 20
scene.render.fps = 30

# Build a deterministic canonical motion, then mimic Proscenium Accept by
# moving it to NLA and clearing the active Action.
source.animation_data_clear()
for pose_bone in source.pose.bones:
    pose_bone.matrix_basis.identity()
    pose_bone.rotation_mode = "QUATERNION"

for frame in (1, 10, 20):
    scene.frame_set(frame)
    phase = (frame - 1) / 19.0
    for pose_bone in source.pose.bones:
        pose_bone.location = Vector((0.0, 0.0, 0.0))
        pose_bone.rotation_quaternion = Quaternion()
        pose_bone.scale = Vector((1.0, 1.0, 1.0))
    source.pose.bones["Hips"].location = Vector((0.28 * phase, 0.04 * math.sin(math.pi * phase), 0.06 * phase))
    source.pose.bones["Hips"].rotation_quaternion = Quaternion((0.0, 0.0, 1.0), math.radians(12.0 * phase))
    source.pose.bones["Chest"].rotation_quaternion = Quaternion((1.0, 0.0, 0.0), math.radians(28.0 * phase))
    source.pose.bones["LeftArm"].rotation_quaternion = Quaternion((0.0, 1.0, 0.0), math.radians(-42.0 * phase))
    source.pose.bones["RightArm"].rotation_quaternion = Quaternion((0.0, 1.0, 0.0), math.radians(22.0 * phase))
    source.pose.bones["LeftLeg"].rotation_quaternion = Quaternion((1.0, 0.0, 0.0), math.radians(20.0 * phase))
    source.pose.bones["LeftShin"].rotation_quaternion = Quaternion((1.0, 0.0, 0.0), math.radians(-35.0 * phase))
    for pose_bone in source.pose.bones:
        pose_bone.keyframe_insert("rotation_quaternion", frame=frame)
    source.pose.bones["Hips"].keyframe_insert("location", frame=frame)

source_action = source.animation_data.action
source_action.name = "Proscenium_Synthetic_Accepted"
source_action.use_fake_user = True
track = source.animation_data.nla_tracks.new()
track.name = "Proscenium: Motion"
accepted_strip = track.strips.new(source_action.name, 1, source_action)
accepted_strip.influence = 1.0
accepted_strip.blend_in = 0.0
accepted_strip.blend_out = 0.0
source.animation_data.action = None
source.animation_data.use_nla = True

source_nla_probe = {
    "use_nla": bool(source.animation_data.use_nla),
    "active_action": getattr(source.animation_data.action, "name", None),
    "tracks": [
        {
            "name": item.name,
            "mute": bool(getattr(item, "mute", False)),
            "solo": bool(getattr(item, "is_solo", False)),
            "strips": [
                {
                    "action": getattr(entry.action, "name", None),
                    "mute": bool(getattr(entry, "mute", False)),
                    "influence": float(getattr(entry, "influence", 1.0)),
                }
                for entry in item.strips
            ],
        }
        for item in source.animation_data.nla_tracks
    ],
    "effective": [entry.name for entry in bridge_ops._effective_nla_strips(source.animation_data)],
}
print("BAM_SOURCE_NLA_PROBE=" + json.dumps(source_nla_probe, ensure_ascii=False))
check(bridge_ops._animation_present(source), "synthetic accepted source NLA was not detected")

fixture_mapping = build_mapping(source, target, "FULL")
fixture_constraint_rows = bridge_ops._mapped_constraint_snapshot(target, fixture_mapping)
for row in fixture_constraint_rows:
    constraint = bridge_ops._constraint_by_identity(target, row)
    constraint.mute = False
    constraint.influence = 1.0

original_target_action = target.animation_data.action if target.animation_data else None
original_target_keys = action_key_count(original_target_action) if original_target_action else 0
original_target_use_nla = bool(target.animation_data.use_nla) if target.animation_data else False
original_target_slot = bridge_ops._action_slot_identifier(
    bridge_ops._action_slot(target.animation_data) if target.animation_data else None
)
original_target_fake_user = bool(original_target_action.use_fake_user) if original_target_action else False
original_constraints = constraint_state(target)
rigidbody_cache = getattr(getattr(scene, "rigidbody_world", None), "point_cache", None)
original_cache_start = int(rigidbody_cache.frame_start) if rigidbody_cache is not None else None
original_timeline_start = int(scene.frame_start)
original_timeline_current = int(scene.frame_current)

settings = scene.ba_motion_bridge_settings
settings.source_rig = source
settings.target_rig = target
settings.root_motion_mode = "FULL"
settings.root_motion_policy = "FULL"
settings.auto_scale = True
settings.world_location = True
settings.use_start_buffer = True
settings.initial_pose_source = "REST"
settings.settle_frames = 10
settings.transition_frames = 20
settings.evaluate_physics_preroll = True

result = bpy.ops.ba_motion_bridge.retarget("EXEC_DEFAULT")
check(result == {"FINISHED"}, f"retarget failed: {result}")
output_action = target.animation_data.action
check(output_action is not None and output_action != original_target_action, "no independent output action")
check(output_action.get("bam_role") == "RETARGET_OUTPUT", "output action tag missing")
check(
    output_action.get("bam_engine") == "Proscenium Motion Bridge Native",
    "native engine tag was not used",
)
check(output_action.use_fake_user, "output action is not protected")
check(action_key_count(output_action) > 100, "output action has too few keys")
check(output_action.get("bam_motion_frame_start") == 1, "formal first frame moved")
check(output_action.get("bam_preroll_frame_start") == -29, "unexpected pre-roll start")
check(output_action.get("bam_preroll_settle_frames") == 10, "settle metadata missing")
check(output_action.get("bam_preroll_transition_frames") == 20, "transition metadata missing")
check(bool(output_action.use_frame_range), "formal action range was not trimmed")
check(int(output_action.frame_start) == 1 and int(output_action.frame_end) == 20, "formal action range changed")
check(scene.frame_start == 0, f"scene start should use Blender's zero clamp: {scene.frame_start}")
check(scene.use_preview_range and scene.frame_preview_start == -29, "negative preview range was not exposed")
check(scene.frame_current == -29, f"scene did not stop at pre-roll start: {scene.frame_current}")
if rigidbody_cache is not None and not bool(getattr(rigidbody_cache, "is_baked", False)):
    check(int(rigidbody_cache.frame_start) <= -29, "rigid-body cache did not include pre-roll")
check(source.animation_data.action is None, "accepted source action was not restored to NLA-only")
check(source.animation_data.use_nla, "source NLA was disabled")
check(track.strips[0].action == source_action, "source NLA strip changed")
if original_target_action is not None:
    check(action_key_count(original_target_action) == original_target_keys, "original target action was modified")

pairs = list(fixture_mapping.pairs)
check(len(pairs) == 24, f"expected 24 pairs, got {len(pairs)}")
check(
    any(pair.source == "LeftLeg" and pair.target in {"足.L", "左足"} for pair in pairs),
    "SOMA thigh did not map to MMD thigh",
)
check(
    not any(pair.source == "LeftLeg" and pair.target in {"ひざ.L", "左ひざ"} for pair in pairs),
    "SOMA thigh was incorrectly mapped to knee",
)

# Rotation delta agreement verifies rest-aware world transfer on a real MMD
# hierarchy with different bone rolls.
scene.frame_set(20)
bpy.context.view_layer.update()
src_rest = (source.matrix_world @ source.data.bones["Chest"].matrix_local).to_quaternion()
src_pose = (source.matrix_world @ source.pose.bones["Chest"].matrix).to_quaternion()
tgt_rest = (target.matrix_world @ target.data.bones["上半身2"].matrix_local).to_quaternion()
tgt_pose = (target.matrix_world @ target.pose.bones["上半身2"].matrix).to_quaternion()
src_delta = src_pose @ src_rest.inverted()
tgt_delta = tgt_pose @ tgt_rest.inverted()
rotation_error = src_delta.rotation_difference(tgt_delta).angle
check(rotation_error < math.radians(2.0), f"world rotation error too large: {math.degrees(rotation_error):.3f} deg")

after_constraints = constraint_state(target)
snapshot_rows = json.loads(settings.constraint_snapshot_json) if settings.constraint_snapshot_json else []
check(len(snapshot_rows) == len(fixture_constraint_rows) and len(snapshot_rows) > 0, "scoped constraints were not snapshotted")
check(output_action.get("bam_disabled_constraint_count") == len(snapshot_rows), "active scoped constraints were not disabled")
snapshot_ids = {f"{row['owner']}\0{row['constraint']}" for row in snapshot_rows}
for identity, state in original_constraints.items():
    if identity not in snapshot_ids:
        check(after_constraints.get(identity) == state, f"unrelated constraint changed: {identity}")

restore = bpy.ops.ba_motion_bridge.restore_constraints("EXEC_DEFAULT") if snapshot_rows else {"FINISHED"}
check(restore == {"FINISHED"}, f"constraint restore failed: {restore}")
check(constraint_state(target) == original_constraints, "constraint snapshot did not restore exact values")
check(not settings.constraint_snapshot_json, "constraint snapshot was not cleared")

restore_target = bpy.ops.ba_motion_bridge.restore_previous_target_animation("EXEC_DEFAULT")
check(restore_target == {"FINISHED"}, f"target animation restore failed: {restore_target}")
check(target.animation_data.action == original_target_action, "original target Action was not rebound")
check(bool(target.animation_data.use_nla) == original_target_use_nla, "target NLA state was not restored")
check(
    bridge_ops._action_slot_identifier(bridge_ops._action_slot(target.animation_data)) == original_target_slot,
    "target Action slot was not restored",
)
if original_target_action is not None:
    check(
        bool(original_target_action.use_fake_user) == original_target_fake_user,
        "original target Action fake-user state was not restored",
    )
check(not settings.previous_target_state_available, "target restore transaction was not cleared")
if rigidbody_cache is not None and original_cache_start is not None:
    check(int(rigidbody_cache.frame_start) == original_cache_start, "physics cache start was not restored")
check(scene.frame_start == original_timeline_start, "scene timeline start was not restored")
check(scene.frame_current == original_timeline_current, "scene current frame was not restored")

# Inject an exception after constraints have been disabled but before native
# bake output is created. Every mutable Bridge-owned state must roll back.
source_state_before_failure = (
    source.animation_data.action,
    bool(source.animation_data.use_nla),
    scene.frame_current,
)
target_state_before_failure = (
    target.animation_data.action,
    bool(target.animation_data.use_nla),
    bridge_ops._action_slot_identifier(bridge_ops._action_slot(target.animation_data)),
)
constraints_before_failure = constraint_state(target)
real_bake = bridge_ops.bake_retarget


def injected_bake(*_args, **_kwargs):
    raise RuntimeError("BAM injected native bake failure")


bridge_ops.bake_retarget = injected_bake
try:
    try:
        failed = bpy.ops.ba_motion_bridge.retarget("EXEC_DEFAULT")
    except RuntimeError as exc:
        check("BAM injected native bake failure" in str(exc), f"unexpected injected error: {exc}")
        failed = {"CANCELLED"}
finally:
    bridge_ops.bake_retarget = real_bake
check(failed == {"CANCELLED"}, f"injected failure unexpectedly succeeded: {failed}")
check(
    (source.animation_data.action, bool(source.animation_data.use_nla), scene.frame_current)
    == source_state_before_failure,
    "source Action/NLA/frame did not roll back",
)
check(
    (
        target.animation_data.action,
        bool(target.animation_data.use_nla),
        bridge_ops._action_slot_identifier(bridge_ops._action_slot(target.animation_data)),
    )
    == target_state_before_failure,
    "target Action/NLA/slot did not roll back",
)
check(constraint_state(target) == constraints_before_failure, "constraints did not roll back")
check(not any(action.get("bam_temporary") for action in bpy.data.actions), "temporary action leaked")

report = {
    "status": "PASS",
    "source": source.name,
    "target": target.name,
    "pairs": len(pairs),
    "scale_ratio": settings.scale_ratio,
    "output_action": output_action.name,
    "output_keys": action_key_count(output_action),
    "formal_motion_range": [int(output_action.frame_start), int(output_action.frame_end)],
    "preroll_start": int(output_action.get("bam_preroll_frame_start")),
    "rotation_error_degrees": math.degrees(rotation_error),
    "scoped_constraints": len(snapshot_rows),
    "source_nla_restored": True,
    "original_action_preserved": True,
    "original_target_state_restored": True,
    "failure_transaction_rolled_back": True,
    "blendcap_loaded": False,
    "temporary_actions": 0,
}
print("BAM_REAL_RETARGET=" + json.dumps(report, ensure_ascii=False))
