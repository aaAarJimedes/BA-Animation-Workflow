from __future__ import annotations

import json
from pathlib import Path
import re
import sys

import bpy


WORKSPACE = Path(r"D:\Agent Workspaces\Agent Tools\BA_Animation_Workflow")
sys.path.insert(0, str(WORKSPACE / "extension"))

from ba_motion_bridge.mapping import build_mapping, is_official_canonical_bones


def vector(value):
    return [round(float(component), 6) for component in value]


def quaternion(value):
    return [round(float(component), 6) for component in value]


def action_name(rig):
    animation_data = rig.animation_data
    if animation_data is None:
        return None
    action = animation_data.action
    return action.name if action is not None else None


def action_probe(action):
    bone_names = []
    arm_curves = []
    for layer in getattr(action, "layers", ()):
        for strip in getattr(layer, "strips", ()):
            for bag in strip.channelbags:
                for curve in bag.fcurves:
                    match = re.match(r'^pose\.bones\["(.+?)"\]', curve.data_path)
                    if match:
                        bone_names.append(match.group(1))
                    if any(token in curve.data_path.lower() for token in ("arm", "forearm", "hand", "ik_fk")):
                        arm_curves.append([curve.data_path, curve.array_index])
    return {
        "name": action.name,
        "frame_range": [round(float(value), 3) for value in action.frame_range],
        "bones": sorted(set(bone_names)),
        "arm_curves": arm_curves,
    }


def bone_probe(rig, bone_name):
    data_bone = rig.data.bones.get(bone_name)
    pose_bone = rig.pose.bones.get(bone_name)
    if data_bone is None or pose_bone is None:
        return None
    rest_world = rig.matrix_world @ data_bone.matrix_local
    pose_world = rig.matrix_world @ pose_bone.matrix
    return {
        "rest_head": vector(rig.matrix_world @ data_bone.head_local),
        "rest_tail": vector(rig.matrix_world @ data_bone.tail_local),
        "pose_head": vector(pose_world.translation),
        "rest_rotation": quaternion(rest_world.to_quaternion()),
        "pose_rotation": quaternion(pose_world.to_quaternion()),
        "delta_rotation": quaternion(
            pose_world.to_quaternion() @ rest_world.to_quaternion().inverted()
        ),
        "rotation_mode": pose_bone.rotation_mode,
    }


scene = bpy.context.scene
armatures = [obj for obj in scene.objects if obj.type == "ARMATURE"]
sources = [
    obj
    for obj in armatures
    if is_official_canonical_bones({bone.name for bone in obj.data.bones})
]
source = sources[0] if len(sources) == 1 else None

summary = {
    "file": bpy.data.filepath,
    "frame": scene.frame_current,
    "armatures": [
        {
            "name": rig.name,
            "bones": len(rig.data.bones),
            "action": action_name(rig),
            "nla_tracks": len(rig.animation_data.nla_tracks) if rig.animation_data else 0,
            "canonical": rig in sources,
        }
        for rig in armatures
    ],
    "actions": [action_probe(action) for action in bpy.data.actions],
}

if source is not None:
    candidates = []
    for target in armatures:
        if target == source:
            continue
        result = build_mapping(source, target, "FULL")
        candidates.append((len(result.critical_missing), -result.matched_count, target.name, target, result))
    if candidates:
        _missing, _matched, _name, target, result = min(candidates)
        summary["source"] = source.name
        summary["target"] = target.name
        summary["mapping"] = [pair.to_dict() for pair in result.pairs]
        summary["critical_missing"] = list(result.critical_missing)
        roles = {pair.role: pair for pair in result.pairs}
        source_bones = {
            role: bone_probe(source, pair.source)
            for role, pair in roles.items()
            if role in {
                "left_shoulder", "left_upper_arm", "left_forearm", "left_hand",
                "right_shoulder", "right_upper_arm", "right_forearm", "right_hand",
            }
        }
        target_bones = {
            role: bone_probe(target, pair.target)
            for role, pair in roles.items()
            if role in source_bones
        }
        summary["source_arm_chain"] = source_bones
        summary["target_arm_chain"] = target_bones
        summary["target_candidate_bones"] = [
            {
                "name": bone.name,
                "parent": bone.parent.name if bone.parent else None,
                "deform": bool(bone.use_deform),
                "mmd_name_j": getattr(getattr(bone, "mmd_bone", None), "name_j", ""),
                "mmd_name_e": getattr(getattr(bone, "mmd_bone", None), "name_e", ""),
                "constraints": [
                    {
                        "name": constraint.name,
                        "type": constraint.type,
                        "subtarget": getattr(constraint, "subtarget", ""),
                        "mute": bool(constraint.mute),
                        "influence": round(float(constraint.influence), 6),
                    }
                    for constraint in target.pose.bones[bone.name].constraints
                ],
            }
            for bone in target.data.bones
            if any(
                token in bone.name.lower()
                for token in (
                    "root", "center", "groove", "hip", "pelvis", "spine", "torso",
                    "chest", "neck", "head", "shoulder", "clav", "arm", "forearm",
                    "hand", "leg", "thigh", "shin", "knee", "foot", "toe",
                )
            )
        ]
        summary["target_arm_controls"] = {
            name: {
                "parent": target.data.bones[name].parent.name if target.data.bones[name].parent else None,
                "rest_head": vector(target.matrix_world @ target.data.bones[name].head_local),
                "pose_head": vector(target.matrix_world @ target.pose.bones[name].matrix.translation),
                "custom_properties": {
                    key: target.pose.bones[name][key]
                    for key in target.pose.bones[name].keys()
                    if key != "_RNA_UI" and isinstance(target.pose.bones[name][key], (bool, int, float, str))
                },
                "constraints": [
                    {
                        "name": constraint.name,
                        "type": constraint.type,
                        "subtarget": getattr(constraint, "subtarget", ""),
                        "influence": round(float(constraint.influence), 6),
                    }
                    for constraint in target.pose.bones[name].constraints
                ],
            }
            for name in (
                "c_shoulder.l", "c_arm_fk.l", "c_forearm_fk.l", "c_hand_fk.l", "c_hand_ik.l",
                "c_shoulder.r", "c_arm_fk.r", "c_forearm_fk.r", "c_hand_fk.r", "c_hand_ik.r",
                "arm.l", "forearm.l", "hand.l", "arm.r", "forearm.r", "hand.r",
            )
            if name in target.pose.bones
        }

print("MOTION_BRIDGE_POSE_PROBE=" + json.dumps(summary, ensure_ascii=False))
