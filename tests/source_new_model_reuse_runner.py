"""Register source add-ons, open the real file, and run new-model Action reuse."""

from pathlib import Path
import os
import runpy
import sys

import bpy
if os.environ.get("BAW_REAL_TIMELINE_TEST") == "1":
    import addon_utils
    addon_utils.enable("proscenium_blender", default_set=False)
    assert hasattr(bpy.context.scene, "proscenium")


workspace = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(workspace / "extension"))

import ba_motion_bridge
import ba_animation_workflow


ba_motion_bridge.register()
ba_animation_workflow.register()
bpy.ops.wm.open_mainfile(filepath=os.environ["BAW_REAL_REUSE_BLEND"])
test_name = os.environ.get("BAW_REAL_SOURCE_TEST", "real_new_model_reuse_test.py")
runpy.run_path(str(workspace / "tests" / test_name), run_name="__main__")
