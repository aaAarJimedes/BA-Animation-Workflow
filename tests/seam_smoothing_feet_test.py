"""Combined options on a supported FK fixture, memory only, never save."""
import bpy, os, runpy
from pathlib import Path
s=bpy.context.scene; cfg=s.baw_auto_director
target=cfg.reuse_target_rig or cfg.target_rig
# The newest real file enables MMD LIMIT_ROTATION overrides. Test the paired
# algorithms in their supported FK configuration without changing the file.
for name in ('ひざ.L','ひざ.R','足首.L','足首.R'):
    for constraint in target.pose.bones[name].constraints:
        if constraint.type=='LIMIT_ROTATION' and constraint.name=='mmd_ik_limit_override':
            constraint.mute=True
os.environ['BAW_SEAM_WITH_FEET']='1'
runpy.run_path(str(Path(__file__).with_name('seam_smoothing_reuse_test.py')),run_name='__main__')
