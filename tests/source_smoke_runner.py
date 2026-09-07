"""Bootstrap the full BA Workflow smoke test from the unpacked source."""

import os
from pathlib import Path
import runpy
import sys


workspace = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(workspace / "extension"))
os.environ["BAW_ADDON_MODULE"] = "ba_animation_workflow"
runpy.run_path(str(workspace / "tests" / "smoke_test.py"), run_name="__main__")
