"""Mount the source Bridge in a disposable real-profile process."""

from pathlib import Path
import runpy

import bpy


# Do not save preferences. Disable installed copies whose operator ids would
# otherwise shadow the source tree under test.
for module_name in (
    "bl_ext.user_default.ba_animation_workflow",
    "bl_ext.user_default.ba_motion_bridge",
    "bl_ext.user_default.proscenium_motion_bridge",
):
    if module_name in bpy.context.preferences.addons:
        result = bpy.ops.preferences.addon_disable(module=module_name)
        if result != {"FINISHED"}:
            raise RuntimeError(f"could not disable installed add-on {module_name}: {result}")

workspace = Path(__file__).resolve().parents[1]
runpy.run_path(
    str(workspace / "tests" / "motion_bridge_real_retarget_smoke.py"),
    run_name="__main__",
)
