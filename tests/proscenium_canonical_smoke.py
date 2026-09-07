from __future__ import annotations

import json
from pathlib import Path
import sys

import bpy

from proscenium_blender import mmcp_client


def script_args() -> list[str]:
    if "--" not in sys.argv:
        return []
    return sys.argv[sys.argv.index("--") + 1 :]


args = script_args()
if len(args) != 1:
    raise RuntimeError("expected one output .blend path")
output = Path(args[0]).resolve()
output.parent.mkdir(parents=True, exist_ok=True)

preferences = bpy.context.preferences.addons["proscenium_blender"].preferences
if bool(getattr(preferences, "self_hosted", False)):
    raise RuntimeError("expected hosted mode")
if bool(getattr(preferences, "access_token", "")):
    raise RuntimeError("fixture smoke must run without account credentials")

client = mmcp_client.MmcpClient(mmcp_client.get_mmcp_url(), timeout=20)
capabilities = client.capabilities(refresh=True)
mmcp_client.store_capabilities(capabilities)
models = [item for item in capabilities.get("models", []) if item.get("canonical_skeleton")]
if not models:
    raise RuntimeError("hosted capabilities returned no canonical skeleton")

model_id = str(models[0]["id"])
settings = bpy.context.scene.proscenium
settings.model_id = model_id

result = bpy.ops.proscenium.import_canonical_skeleton(with_body=False)
if "FINISHED" not in result:
    raise RuntimeError(f"canonical skeleton import failed: {sorted(result)}")

armature = settings.target_armature
if armature is None or armature.type != "ARMATURE":
    raise RuntimeError("import did not assign an armature target")
bone_count = len(armature.data.bones)
if bone_count < 20:
    raise RuntimeError(f"canonical skeleton is unexpectedly small: {bone_count} bones")
if armature.get("proscenium_canonical_model") != model_id:
    raise RuntimeError("canonical model marker missing")

bpy.context.scene.render.fps = 30
bpy.context.scene.render.fps_base = 1.0
bpy.ops.wm.save_as_mainfile(filepath=str(output), check_existing=False)

report = {
    "status": "PASS",
    "endpoint": mmcp_client.get_mmcp_url(),
    "model_id": model_id,
    "armature": armature.name,
    "bone_count": bone_count,
    "fps": bpy.context.scene.render.fps,
    "signed_in": False,
    "saved_file": str(output),
}
print("PROSCENIUM_CANONICAL_SMOKE=" + json.dumps(report, ensure_ascii=False))
