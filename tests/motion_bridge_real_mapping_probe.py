from __future__ import annotations

import json
import importlib
import os
from pathlib import Path
import sys

import bpy


if not bpy.app.background:
    raise RuntimeError("Real mapping probe refuses to run in Blender UI")
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
build_mapping = importlib.import_module(bridge_module_name + ".mapping").build_mapping


if not hasattr(bpy.types.Scene, "ba_motion_bridge_settings"):
    ba_motion_bridge.register()

source = bpy.data.objects.get("kimodo-soma-rp")
if source is None:
    with bpy.data.libraries.load(str(CANONICAL_BLEND), link=False) as (data_from, data_to):
        data_to.objects = ["kimodo-soma-rp"] if "kimodo-soma-rp" in data_from.objects else []
    source = next(obj for obj in data_to.objects if obj is not None)
    bpy.context.scene.collection.objects.link(source)

target = bpy.data.objects.get("星野（二年级）_arm")
if target is None:
    candidates = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE" and obj != source]
    target = max(candidates, key=lambda obj: sum(1 for bone in obj.data.bones if any(ch > "\x7f" for ch in bone.name)))

result = build_mapping(source, target, "FULL")
payload = {
    "source": source.name,
    "target": target.name,
    "matched": result.matched_count,
    "expected": result.expected_count,
    "critical_missing": list(result.critical_missing),
    "missing": list(result.missing),
    "warnings": list(result.warnings),
    "pairs": [pair.to_dict() for pair in result.pairs],
}
print("BAM_REAL_MAPPING=" + json.dumps(payload, ensure_ascii=False))

if result.critical_missing:
    raise RuntimeError("critical mapping gaps: " + ", ".join(result.critical_missing))
if result.matched_count < 20:
    raise RuntimeError(f"unexpectedly low coverage: {result.matched_count}")
if any(
    token in pair.target.lower()
    for pair in result.pairs
    for token in ("ik", "ｉｋ", "捩", "twist", "shadow")
):
    raise RuntimeError("mapping selected an IK/twist/shadow target")
