from __future__ import annotations

import json
import os
import re

import bpy
from mathutils import Vector


if not bpy.app.background:
    raise RuntimeError("Foot deformation inspection refuses to run in Blender UI")
if os.environ.get("BAW_FOOT_INSPECT_ALLOW") != "read-only-background-test":
    raise RuntimeError("Set BAW_FOOT_INSPECT_ALLOW=read-only-background-test explicitly")


FOOT_WORDS = ("足首", "つま先", "足ＩＫ", "足IK", "toe", "foot", "ankle")
LEFT_WORDS = ("左", "left", ".l", "_l")
RIGHT_WORDS = ("右", "right", ".r", "_r")
POSE_PATH = re.compile(r'^pose\.bones\["((?:\\.|[^"\\])*)"\]\.(.+)$')


def is_foot(name: str) -> bool:
    folded = name.casefold()
    return any(word.casefold() in folded for word in FOOT_WORDS)


def side_of(name: str):
    folded = name.casefold()
    if any(word.casefold() in folded for word in LEFT_WORDS):
        return "LEFT"
    if any(word.casefold() in folded for word in RIGHT_WORDS):
        return "RIGHT"
    return None


def dims(points):
    if not points:
        return None
    minima = [min(point[index] for point in points) for index in range(3)]
    maxima = [max(point[index] for point in points) for index in range(3)]
    return [maxima[index] - minima[index] for index in range(3)]


def ratios(values, baseline):
    if values is None or baseline is None:
        return None
    return [
        values[index] / baseline[index] if baseline[index] > 1e-8 else None
        for index in range(3)
    ]


def iter_action_fcurves(action):
    legacy = getattr(action, "fcurves", None)
    if legacy is not None:
        yield from legacy
        return
    for layer in getattr(action, "layers", ()):
        for strip in getattr(layer, "strips", ()):
            for slot in getattr(action, "slots", ()):
                try:
                    channelbag = strip.channelbag(slot)
                except (AttributeError, RuntimeError, TypeError):
                    channelbag = None
                if channelbag is not None:
                    yield from channelbag.fcurves


scene = bpy.context.scene
depsgraph = bpy.context.evaluated_depsgraph_get()
armatures = [obj for obj in scene.objects if obj.type == "ARMATURE"]
targets = []
for armature in armatures:
    animation = armature.animation_data
    actions = []
    if animation is not None and animation.action is not None:
        actions.append(animation.action)
    if animation is not None:
        actions.extend(
            strip.action
            for track in animation.nla_tracks
            for strip in track.strips
            if strip.action is not None
        )
    if any(action.get("bam_role") == "RETARGET_OUTPUT" for action in actions):
        targets.append((armature, list(dict.fromkeys(actions))))

result = {"file": bpy.data.filepath, "scene": scene.name, "targets": []}
sample_frames = sorted({
    int(scene.frame_start),
    int(scene.frame_end),
    1, 40, 75, 120, 149, 150, 180, 223, 224, 260, 293,
})
sample_frames = [frame for frame in sample_frames if -1000 <= frame <= max(1000, scene.frame_end)]

for target, actions in targets:
    animation = target.animation_data
    target_row = {
        "name": target.name,
        "object_scale": list(target.scale),
        "matrix_world_scale": list(target.matrix_world.to_scale()),
        "active_action": animation.action.name if animation and animation.action else None,
        "use_nla": bool(animation and animation.use_nla),
        "nla": [
            {
                "track": track.name,
                "action": strip.action.name if strip.action else None,
                "frame": [float(strip.frame_start), float(strip.frame_end)],
                "blend": strip.blend_type,
                "extrapolation": strip.extrapolation,
            }
            for track in animation.nla_tracks
            for strip in track.strips
        ],
        "actions": [],
        "foot_bones": [],
        "meshes": [],
    }
    for action in actions:
        scale_curves = []
        foot_curves = []
        for curve in iter_action_fcurves(action):
            match = POSE_PATH.match(curve.data_path)
            bone_name = match.group(1) if match else ""
            channel = match.group(2) if match else curve.data_path
            row = {
                "bone": bone_name,
                "channel": channel,
                "index": curve.array_index,
                "keys": len(curve.keyframe_points),
                "min": min((float(key.co[1]) for key in curve.keyframe_points), default=None),
                "max": max((float(key.co[1]) for key in curve.keyframe_points), default=None),
            }
            if channel == "scale":
                scale_curves.append(row)
            if is_foot(bone_name):
                foot_curves.append(row)
        target_row["actions"].append({
            "name": action.name,
            "range": [float(value) for value in action.frame_range],
            "motion_range": [
                action.get("bam_motion_frame_start"),
                action.get("bam_motion_frame_end"),
            ],
            "scale_curves": scale_curves,
            "foot_curves": foot_curves,
        })

    foot_bones = [bone for bone in target.pose.bones if is_foot(bone.name)]
    for bone in foot_bones:
        target_row["foot_bones"].append({
            "name": bone.name,
            "parent": bone.parent.name if bone.parent else None,
            "inherit_scale": str(bone.bone.inherit_scale),
            "constraints": [
                {
                    "name": constraint.name,
                    "type": constraint.type,
                    "mute": bool(constraint.mute),
                    "influence": float(constraint.influence),
                    "target": getattr(getattr(constraint, "target", None), "name", None),
                    "subtarget": str(getattr(constraint, "subtarget", "") or ""),
                }
                for constraint in bone.constraints
            ],
        })

    meshes = [
        obj
        for obj in scene.objects
        if obj.type == "MESH"
        and any(modifier.type == "ARMATURE" and modifier.object == target for modifier in obj.modifiers)
    ]
    for mesh_obj in meshes:
        group_names = {group.index: group.name for group in mesh_obj.vertex_groups}
        side_vertices = {"LEFT": set(), "RIGHT": set()}
        side_bones = {}
        for side in side_vertices:
            candidates = [bone for bone in foot_bones if side_of(bone.name) == side]
            ankle = next((bone for bone in candidates if "足首" in bone.name or "ankle" in bone.name.casefold()), None)
            side_bones[side] = ankle or (candidates[0] if candidates else None)
        for vertex in mesh_obj.data.vertices:
            for membership in vertex.groups:
                name = group_names.get(membership.group, "")
                side = side_of(name)
                if side and is_foot(name) and membership.weight >= 0.05:
                    side_vertices[side].add(vertex.index)
        if not any(side_vertices.values()):
            continue
        mesh_row = {"name": mesh_obj.name, "sides": {}}
        for side, indices in side_vertices.items():
            bone = side_bones[side]
            if bone is None or not indices:
                continue
            rest_inverse = bone.bone.matrix_local.inverted_safe()
            rest_points = [
                rest_inverse
                @ (target.matrix_world.inverted_safe() @ (mesh_obj.matrix_world @ mesh_obj.data.vertices[index].co))
                for index in sorted(indices)
            ]
            baseline = dims(rest_points)
            samples = []
            for frame in sample_frames:
                scene.frame_set(frame)
                bpy.context.view_layer.update()
                evaluated_target = target.evaluated_get(depsgraph)
                evaluated_mesh = mesh_obj.evaluated_get(depsgraph)
                evaluated_bone = evaluated_target.pose.bones.get(bone.name)
                if evaluated_bone is None or len(evaluated_mesh.data.vertices) <= max(indices):
                    continue
                inverse_pose = evaluated_bone.matrix.inverted_safe()
                points = [
                    inverse_pose
                    @ (
                        evaluated_target.matrix_world.inverted_safe()
                        @ (evaluated_mesh.matrix_world @ evaluated_mesh.data.vertices[index].co)
                    )
                    for index in sorted(indices)
                ]
                measured = dims(points)
                basis_scale = list(evaluated_bone.matrix_basis.to_scale())
                samples.append({
                    "frame": frame,
                    "dims": measured,
                    "ratio": ratios(measured, baseline),
                    "basis_scale": basis_scale,
                    "basis_determinant": float(evaluated_bone.matrix_basis.to_3x3().determinant()),
                })
            mesh_row["sides"][side] = {
                "bone": bone.name,
                "vertex_count": len(indices),
                "rest_dims": baseline,
                "samples": samples,
            }
        target_row["meshes"].append(mesh_row)
    result["targets"].append(target_row)

result["saved"] = False
result["cloud_generation_invoked"] = False
print("BAW_FOOT_DEFORMATION_INSPECT=" + json.dumps(result, ensure_ascii=False, default=str))
