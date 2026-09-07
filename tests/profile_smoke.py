from __future__ import annotations

import importlib
import json
from pathlib import Path
import tomllib

import addon_utils
import bpy


def module_state(module_name: str) -> tuple[bool, bool]:
    return tuple(bool(value) for value in addon_utils.check(module_name))


enabled = sorted(addon.module for addon in bpy.context.preferences.addons)
states = {module: module_state(module) for module in enabled}


def find_enabled(*final_names: str) -> list[str]:
    wanted = {name.lower() for name in final_names}
    return [
        module
        for module in enabled
        if module.lower() in wanted or module.rsplit(".", 1)[-1].lower() in wanted
    ]


expected = {
    "BlendCap": find_enabled("blendcap"),
    "MMD Tools": find_enabled("mmd_tools", "blender_mmd_tools"),
    "BlendCap Motion Bridge": find_enabled("blendcap_motion_bridge"),
    "Proscenium": find_enabled("proscenium_blender"),
    "BA Animation Workflow": find_enabled("ba_animation_workflow"),
    "Proscenium Motion Bridge": find_enabled("proscenium_motion_bridge"),
    "Add Camera Rigs": find_enabled("add_camera_rigs"),
}

errors: list[str] = []
for label, modules in expected.items():
    if not modules:
        errors.append(f"{label} not enabled")
        continue
    if not any(states[module] == (True, True) for module in modules):
        errors.append(f"{label} enabled but not loaded: {modules}")


def imported(label: str):
    modules = expected.get(label, ())
    if not modules:
        return None
    try:
        return importlib.import_module(modules[0])
    except ImportError as exc:
        errors.append(f"could not import {label}: {exc}")
        return None


def manifest_version(module) -> tuple[int, ...] | None:
    if module is None or not getattr(module, "__file__", None):
        return None
    manifest = Path(module.__file__).resolve().parent / "blender_manifest.toml"
    if not manifest.is_file():
        return None
    value = tomllib.loads(manifest.read_text(encoding="utf-8")).get("version", "")
    try:
        return tuple(int(part) for part in value.split("."))
    except ValueError:
        return None


versions: dict[str, list[int] | None] = {}
version_expectations = {
    "BlendCap": (1, 0, 5),
    "BlendCap Motion Bridge": (0, 4, 0),
    "BA Animation Workflow": (0, 9, 0),
    "Proscenium Motion Bridge": (0, 9, 1),
}
for label, expected_version in version_expectations.items():
    module = imported(label)
    if module is None:
        continue
    if label in {"BA Animation Workflow", "Proscenium Motion Bridge"}:
        try:
            version = tuple(importlib.import_module(module.__name__ + ".constants").ADDON_VERSION)
        except (AttributeError, ImportError) as exc:
            errors.append(f"could not read {label} version: {exc}")
            continue
    else:
        version = manifest_version(module)
    versions[label] = list(version) if version is not None else None
    if version != expected_version:
        errors.append(f"unexpected {label} version: {version}; expected {expected_version}")

proscenium_module = imported("Proscenium")
if proscenium_module is not None:
    proscenium_version = tuple(getattr(proscenium_module, "bl_info", {}).get("version", ()))
    versions["Proscenium"] = list(proscenium_version)
    if proscenium_version != (0, 4, 0):
        errors.append(f"unexpected Proscenium version: {proscenium_version}")

animaide_modules = find_enabled("animaide")
if animaide_modules:
    errors.append("stale animaide preference still enabled")

legacy_modules = find_enabled("mmd2blendcap", "ba_motion_bridge")
if legacy_modules:
    errors.append(f"legacy extension IDs still enabled: {legacy_modules}")

required_operator_names = (
    "baw.initialize_workflow",
    "baw.setup_scene",
    "baw.clean_mocap_action",
    "baw.create_camera_rig",
    "baw.cleanup_bridge_temporary",
    "baw.auto_compile_plan",
    "baw.auto_prompt_new",
    "baw.auto_prompt_unlink",
    "baw.auto_prompt_edit",
    "baw.auto_build_scene",
    "baw.auto_remap_existing",
    "baw.auto_import_existing",
    "baw.auto_import_all_existing",
    "baw.auto_run",
    "baw.auto_finalize_preview",
    "baw.auto_cancel",
    "baw.auto_clear_scene",
    "object.build_camera_rig",
    "blendcap.apply_retarget",
    "blendcap_motion_bridge.detect",
    "blendcap_motion_bridge.auto_select",
    "blendcap_motion_bridge.prepare_in_memory",
    "blendcap_motion_bridge.quick_retarget",
    "blendcap_motion_bridge.apply_retarget_fk_safe",
    "blendcap_motion_bridge.restore_leg_overrides",
    "blendcap_motion_bridge.restore_previous_state",
    "proscenium.connect",
    "proscenium.import_canonical_skeleton",
    "proscenium.generate",
    "proscenium.generate_pose",
    "proscenium.accept",
    "proscenium.reject",
    "ba_motion_bridge.auto_map",
    "ba_motion_bridge.prepare_from_proscenium",
    "ba_motion_bridge.accept_and_retarget",
    "ba_motion_bridge.activate_output",
    "ba_motion_bridge.validate_mapping",
    "ba_motion_bridge.retarget",
    "ba_motion_bridge.restore_constraints",
    "ba_motion_bridge.restore_previous_target_animation",
    "ba_motion_bridge.restore_previous_state",
    "ba_motion_bridge.cleanup_temporary",
)
for name in required_operator_names:
    namespace, operator_name = name.split(".", 1)
    try:
        getattr(getattr(bpy.ops, namespace), operator_name).get_rna_type()
    except (AttributeError, KeyError, RuntimeError):
        errors.append(f"operator unavailable: {name}")

required_scene_rna = (
    "baw_settings",
    "baw_auto_director",
    "ba_motion_bridge_settings",
    "blendcap_retarget_pairs",
    "blendcap_retarget_source",
    "blendcap_retarget_target",
    "proscenium",
)
for name in required_scene_rna:
    if not hasattr(bpy.types.Scene, name):
        errors.append(f"Scene RNA unavailable: {name}")

required_panels = (
    "BAM_PT_proscenium_motion_bridge",
    "BAW_PT_main",
)
for name in required_panels:
    if not hasattr(bpy.types, name):
        errors.append(f"Panel unavailable: {name}")

workflow_panels = sorted(name for name in dir(bpy.types) if name.startswith("BAW_PT_"))
if workflow_panels != ["BAW_PT_main"]:
    errors.append(f"redundant BA Workflow panels registered: {workflow_panels}")

result = {
    "status": "PASS" if not errors else "FAIL",
    "blender": bpy.app.version_string,
    "expected_modules": expected,
    "states": {module: list(states[module]) for modules in expected.values() for module in modules},
    "animaide_enabled": bool(animaide_modules),
    "legacy_modules_enabled": legacy_modules,
    "versions": versions,
    "required_operator_count": len(required_operator_names),
    "required_scene_rna": list(required_scene_rna),
    "required_panels": list(required_panels),
    "workflow_panels": workflow_panels,
    "errors": errors,
}
print("BAW_PROFILE_SMOKE=" + json.dumps(result, ensure_ascii=False))

if errors:
    raise RuntimeError("; ".join(errors))
