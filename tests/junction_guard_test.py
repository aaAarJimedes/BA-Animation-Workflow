from __future__ import annotations

import importlib
import os
from pathlib import Path

import bpy


if not bpy.app.background:
    raise RuntimeError("Junction guard test is background-only")

module = importlib.import_module(os.environ["BAW_ADDON_MODULE"])
if not hasattr(bpy.types.Scene, "baw_settings"):
    module.register()

project_root = Path(os.environ["BAW_TEST_PROJECT"]).resolve()
victim = Path(os.environ["BAW_JUNCTION_VICTIM"]).resolve()
bpy.context.scene.baw_settings.project_root = str(project_root)

if module.utils.cache_is_safe(project_root, project_root / "50_cache" / "baw_generated"):
    raise AssertionError("Junction passed the cache utility safety check")

try:
    result = bpy.ops.baw.cleanup_cache("EXEC_DEFAULT")
except RuntimeError as exc:
    if "安全检查失败" not in str(exc):
        raise AssertionError(f"Unexpected cleanup error: {exc}") from exc
    result = {"CANCELLED"}

if result != {"CANCELLED"}:
    raise AssertionError(f"Junction cleanup was not blocked: {result}")
if not victim.is_file():
    raise AssertionError("Junction target file was deleted")

print(f"BAW_JUNCTION_GUARD=PASS victim={victim}")
