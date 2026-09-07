from __future__ import annotations

import importlib
import os
from pathlib import Path

import bpy


if not bpy.app.background:
    raise RuntimeError("Dangling link test is background-only")

module = importlib.import_module(os.environ["BAW_ADDON_MODULE"])
if not hasattr(bpy.types.Scene, "baw_settings"):
    module.register()

fixture_root = Path(os.environ["BAW_TEST_PROJECT"])
marker_link = fixture_root / ".baw_workspace"
marker_target = Path(os.environ["BAW_DANGLING_MARKER_TARGET"])
if not os.path.lexists(marker_link) or marker_link.exists():
    raise AssertionError("Workspace marker fixture is not a dangling link")

try:
    module.utils.create_project_folders(fixture_root)
except ValueError as exc:
    if "符号链接" not in str(exc) and "重解析点" not in str(exc):
        raise AssertionError(f"Unexpected dangling marker error: {exc}") from exc
else:
    raise AssertionError("Dangling workspace marker was followed")
if marker_target.exists():
    raise AssertionError("Workspace marker target was created")

root_target = Path(os.environ["BAW_DANGLING_ROOT_TARGET"])
root_link = Path(os.environ["BAW_DANGLING_ROOT"])
if not os.path.lexists(root_link) or root_link.exists():
    raise AssertionError("Project root fixture is not a dangling link")
try:
    module.utils.validate_project_root(root_link)
except ValueError as exc:
    if "符号链接" not in str(exc) and "目录联接" not in str(exc):
        raise AssertionError(f"Unexpected dangling root error: {exc}") from exc
else:
    raise AssertionError("Dangling project root was followed")
if root_target.exists():
    raise AssertionError("Dangling project root target was created")

print("BAW_DANGLING_LINK_GUARD=PASS")
