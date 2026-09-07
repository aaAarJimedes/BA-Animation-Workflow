"""Run the ARP regression against the installed release package."""

import os
from pathlib import Path
import runpy
import sys


installed_root = Path(
    r"C:\Users\Administrator\AppData\Roaming\Blender Foundation\Blender\5.1\extensions\user_default"
)
sys.path.insert(0, str(installed_root))
os.environ["BAM_BRIDGE_MODULE"] = "proscenium_motion_bridge"

workspace = Path(__file__).resolve().parents[1]
runpy.run_path(
    str(workspace / "tests" / "motion_bridge_arp_pose_regression.py"),
    run_name="__main__",
)
