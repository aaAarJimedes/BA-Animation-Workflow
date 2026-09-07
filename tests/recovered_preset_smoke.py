from __future__ import annotations

import hashlib
import json

import bpy


EXPECTED_PATH = (
    r"C:\Users\Administrator\AppData\Roaming\Blender Foundation\Blender\5.1\config"
    r"\blendcap\retarget_maps\blendcap_motion_bridge_星野_二年级_arm.json"
)
EXPECTED_PAIRSET_SHA256 = "C509CDCF748221BED62B935D6EA78F36395A8F6AC57CE2EC95ED21C87B5085B3"


def canonical_hash(pairs: list[dict]) -> str:
    encoded = json.dumps(
        pairs,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest().upper()


scene = bpy.context.scene
source = bpy.data.objects.get("9-星野_BHR")
target = bpy.data.objects.get("星野（二年级）_arm")
if source is None or target is None:
    raise RuntimeError("expected source/target rigs are missing from recovery fixture")

scene.blendcap_retarget_source = source
scene.blendcap_retarget_target = target
scene.blendcap_retarget_pairs.clear()
scene.blendcap_retarget_preset = EXPECTED_PATH

pairs = []
for pair in scene.blendcap_retarget_pairs:
    row = {
        "source": pair.source,
        "target": pair.target,
        "channels": pair.channels,
        "influence": float(pair.influence),
    }
    if pair.channels in {"LOC", "LOC_ROT"} and pair.axes != "XYZ":
        row["axes"] = pair.axes
    pairs.append(row)

pairset_hash = canonical_hash(pairs)
missing_sources = sorted({row["source"] for row in pairs if row["source"] not in source.data.bones})
missing_targets = sorted({row["target"] for row in pairs if row["target"] not in target.data.bones})
if len(pairs) != 54:
    raise RuntimeError(f"recovered preset loaded {len(pairs)} pairs instead of 54")
if pairset_hash != EXPECTED_PAIRSET_SHA256:
    raise RuntimeError(f"recovered pairset hash mismatch: {pairset_hash}")
if missing_sources or missing_targets:
    raise RuntimeError(f"invalid references: sources={missing_sources}, targets={missing_targets}")

report = {
    "status": "PASS",
    "preset": EXPECTED_PATH,
    "pairs": len(pairs),
    "normalized_pairset_sha256": pairset_hash,
    "missing_sources": missing_sources,
    "missing_targets": missing_targets,
}
print("MMD_RECOVERED_PRESET_SMOKE=" + json.dumps(report, ensure_ascii=False))
