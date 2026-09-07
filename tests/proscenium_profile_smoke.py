from __future__ import annotations

import importlib
import json
from pathlib import Path
import sys

import addon_utils
import bpy


MODULE = "proscenium_blender"
EXPECTED_VERSION = (0, 4, 0)


def script_args() -> list[str]:
    if "--" not in sys.argv:
        return []
    return sys.argv[sys.argv.index("--") + 1 :]


def operator_available(path: str) -> bool:
    namespace, name = path.split(".", 1)
    operator = getattr(getattr(bpy.ops, namespace), name)
    try:
        operator.get_rna_type()
    except (AttributeError, KeyError, RuntimeError):
        return False
    return True


args = script_args()
cycle_registration = "--cycle-registration" in args
save_path: Path | None = None
if "--save" in args:
    index = args.index("--save")
    save_path = Path(args[index + 1]).resolve()

errors: list[str] = []
state = tuple(bool(value) for value in addon_utils.check(MODULE))
if state != (True, True):
    errors.append(f"addon state is {state}, expected (True, True)")

module = importlib.import_module(MODULE)
version = tuple(module.bl_info.get("version", ()))
if version != EXPECTED_VERSION:
    errors.append(f"unexpected version: {version}")

required_operators = (
    "proscenium.connect",
    "proscenium.generate",
    "proscenium.accept",
    "proscenium.reject",
    "proscenium.signin",
    "proscenium.signout",
    "proscenium.import_canonical_skeleton",
)
missing_operators = [name for name in required_operators if not operator_available(name)]
if missing_operators:
    errors.append(f"missing operators: {missing_operators}")

if not hasattr(bpy.types.Scene, "proscenium"):
    errors.append("Scene.proscenium is not registered")

preferences = bpy.context.preferences.addons[MODULE].preferences
if bool(getattr(preferences, "self_hosted", False)):
    errors.append("addon is not in hosted mode")

# Report only whether a token exists. Never print credentials or token values.
signed_in = bool(getattr(preferences, "access_token", ""))

if cycle_registration:
    # Persist the temporary disabled state so addon_utils.check() reports
    # (False, False), then restore the enabled preference immediately.
    addon_utils.disable(MODULE, default_set=True)
    disabled_state = tuple(bool(value) for value in addon_utils.check(MODULE))
    if disabled_state != (False, False):
        errors.append(f"unregister cycle failed: {disabled_state}")
    addon_utils.enable(MODULE, default_set=True, persistent=True)
    reenabled_state = tuple(bool(value) for value in addon_utils.check(MODULE))
    if reenabled_state != (True, True):
        errors.append(f"re-register cycle failed: {reenabled_state}")
    bpy.ops.wm.save_userpref()

if save_path is not None:
    save_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(save_path), check_existing=False)

result = {
    "status": "PASS" if not errors else "FAIL",
    "blender": bpy.app.version_string,
    "module": MODULE,
    "version": list(version),
    "state": list(state),
    "hosted_mode": not bool(getattr(preferences, "self_hosted", False)),
    "signed_in": signed_in,
    "required_operators": list(required_operators),
    "missing_operators": missing_operators,
    "registration_cycle": cycle_registration,
    "saved_file": str(save_path) if save_path else None,
    "errors": errors,
}
print("PROSCENIUM_SMOKE=" + json.dumps(result, ensure_ascii=False))

if errors:
    raise RuntimeError("; ".join(errors))
