from __future__ import annotations

import importlib
import os
from pathlib import Path

import bpy


if not bpy.app.background:
    raise RuntimeError("Setup junction test is background-only")

module = importlib.import_module(os.environ["BAW_ADDON_MODULE"])
if not hasattr(bpy.types.Scene, "baw_settings"):
    module.register()

project_root = Path(os.environ["BAW_TEST_PROJECT"])
victim = Path(os.environ["BAW_JUNCTION_VICTIM"])
bpy.context.scene.baw_settings.project_root = str(project_root)

try:
    module.utils.create_project_folders(project_root)
except ValueError as exc:
    if "目录联接" not in str(exc) and "符号链接" not in str(exc):
        raise AssertionError(f"Unexpected utility error: {exc}") from exc
else:
    raise AssertionError("Utility followed a child junction")

try:
    result = bpy.ops.baw.setup_project()
except RuntimeError as exc:
    if "目录联接" not in str(exc) and "符号链接" not in str(exc):
        raise AssertionError(f"Unexpected setup error: {exc}") from exc
    result = {"CANCELLED"}

if result != {"CANCELLED"}:
    raise AssertionError(f"Setup followed a child junction: {result}")
if not victim.is_file():
    raise AssertionError("Setup changed the junction target")
if (project_root / ".baw_workspace").exists():
    raise AssertionError("Setup claimed a project containing a child junction")

print(f"BAW_SETUP_JUNCTION_GUARD=PASS victim={victim}")
