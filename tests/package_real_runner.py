"""Run the real retarget regression against an unpacked release package."""

import os
from pathlib import Path
import runpy
import sys


package_parent = Path(os.environ["BAM_PACKAGE_PARENT"]).resolve()
package = package_parent / "proscenium_motion_bridge"
if not (package / "blender_manifest.toml").is_file():
    raise RuntimeError(f"unpacked release package not found: {package}")

sys.path.insert(0, str(package_parent))
os.environ["BAM_BRIDGE_MODULE"] = "proscenium_motion_bridge"

workspace = Path(__file__).resolve().parents[1]
runpy.run_path(str(workspace / "tests" / "real_source_runner.py"), run_name="__main__")
