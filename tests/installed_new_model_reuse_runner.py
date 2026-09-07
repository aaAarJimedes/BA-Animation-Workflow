"""Enable the installed release, open the real file, and run new-model reuse."""

from pathlib import Path
import os
import runpy

import bpy


for module_name in (
    "bl_ext.user_default.proscenium_motion_bridge",
    "bl_ext.user_default.ba_animation_workflow",
):
    if module_name not in bpy.context.preferences.addons:
        result = bpy.ops.preferences.addon_enable(module=module_name)
        if result != {"FINISHED"}:
            raise RuntimeError(f"Could not enable installed add-on {module_name}: {result}")

workspace = Path(__file__).resolve().parents[1]
bpy.ops.wm.open_mainfile(filepath=os.environ["BAW_REAL_REUSE_BLEND"])
os.environ.setdefault("BAW_AUTO_ADDON_MODULE", "bl_ext.user_default.ba_animation_workflow")
test_name = os.environ.get("BAW_REAL_INSTALLED_TEST", "real_new_model_reuse_test.py")
runpy.run_path(str(workspace / "tests" / test_name), run_name="__main__")
