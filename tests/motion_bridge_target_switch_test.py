from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
import sys

import bpy


if not bpy.app.background:
    raise RuntimeError("Target-switch test refuses to run in Blender UI")
if os.environ.get("BAM_SWITCH_TEST_ALLOW") != "isolated-factory-test":
    raise RuntimeError("Set BAM_SWITCH_TEST_ALLOW=isolated-factory-test explicitly")

WORKSPACE = Path(r"D:\Agent Workspaces\Agent Tools\BA_Animation_Workflow")
sys.path.insert(0, os.environ.get("BAM_BRIDGE_IMPORT_ROOT", str(WORKSPACE / "extension")))
module_name = os.environ.get("BAM_BRIDGE_MODULE", "ba_motion_bridge")
addon = importlib.import_module(module_name)
addon.register()
operators = importlib.import_module(module_name + ".operators")


def check(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


scene = bpy.context.scene
settings = scene.ba_motion_bridge_settings

old_data = bpy.data.armatures.new("OldTargetData")
old_target = bpy.data.objects.new("OldTarget", old_data)
new_data = bpy.data.armatures.new("NewTargetData")
new_target = bpy.data.objects.new("NewTarget", new_data)
scene.collection.objects.link(old_target)
scene.collection.objects.link(new_target)

old_action = bpy.data.actions.new("OldTargetPreviousAction")
old_action.use_fake_user = True
settings.target_rig = new_target
settings.previous_target_state_available = True
settings.previous_target_rig = old_target
settings.previous_target_action = old_action
settings.previous_target_action_name = old_action.name
settings.previous_target_action_fake_user = False
settings.constraint_snapshot_json = "[]"
settings.constraint_snapshot_target = old_target.name
settings.constraint_snapshot_target_rig = old_target
settings.target_switch_snapshot_json = "[]"
settings.target_switch_snapshot_target = old_target.name
settings.physics_cache_snapshot_json = '{"present": false}'
settings.timeline_snapshot_json = '{"frame_start": 1}'
settings.last_output_action = "KeptOutput"

result = bpy.ops.ba_motion_bridge.resolve_target_switch("EXEC_DEFAULT", mode="KEEP")
check(result == {"FINISHED"}, f"keep-output resolution failed: {result}")
check(settings.target_rig == new_target, "new target selection changed")
check(not settings.previous_target_state_available, "old target recovery slot was not released")
check(not settings.constraint_snapshot_json, "constraint rollback snapshot was not released")
check(not settings.timeline_snapshot_json, "timeline rollback snapshot was not released")
check(settings.last_output_action == "KeptOutput", "kept output marker was lost")
check(not old_action.use_fake_user, "old baseline Action fake-user state was not normalized")

# The safer resolution restores the old character through its stored pointer,
# while preserving the newly selected target for the next mapping pass.
output_action = bpy.data.actions.new("OldTargetBridgeOutput")
animation_data = old_target.animation_data_create()
operators._bind_action(animation_data, output_action)
settings.previous_target_state_available = True
settings.previous_target_rig = old_target
settings.previous_target_action = old_action
settings.previous_target_action_name = old_action.name
settings.previous_target_action_fake_user = False
settings.previous_target_use_nla = False
settings.physics_cache_snapshot_json = '{"present": false}'
settings.timeline_snapshot_json = json.dumps(
    {
        "frame_start": 1,
        "frame_current": 1,
        "use_preview_range": False,
        "frame_preview_start": 1,
        "frame_preview_end": 250,
    }
)
scene.frame_start = 0
scene.use_preview_range = True
scene.frame_preview_start = -5
scene.frame_set(-5)
settings.target_rig = new_target

result = bpy.ops.ba_motion_bridge.resolve_target_switch("EXEC_DEFAULT", mode="RESTORE")
check(result == {"FINISHED"}, f"restore-first resolution failed: {result}")
check(old_target.animation_data.action == old_action, "old target Action was not restored")
check(settings.target_rig == new_target, "new target selection was not preserved after restore")
check(scene.frame_start == 1 and scene.frame_current == 1, "timeline was not restored before switching")
check(not scene.use_preview_range, "preview-range state was not restored")

# Re-activation must use the progress lifecycle even when no rigid-body world
# exists, and it must always clear the transient progress UI state.
kept_action = bpy.data.actions.new(settings.last_output_action)
kept_action["bam_motion_frame_start"] = 1
kept_action["bam_preroll_frame_start"] = -2
kept_action["bam_target_object"] = old_target.name
settings.target_rig = new_target
activate = bpy.ops.ba_motion_bridge.activate_output("EXEC_DEFAULT")
check(activate == {"FINISHED"}, f"output activation failed: {activate}")
check(old_target.animation_data.action == kept_action, "output was not reactivated on its recorded target")
check(new_target.animation_data is None or new_target.animation_data.action != kept_action, "output leaked to current wrong target")
check(not settings.progress_active, "activation left progress UI stuck")

print(
    "PMB_TARGET_SWITCH_TEST="
    + json.dumps(
        {
            "status": "PASS",
            "target": settings.target_rig.name,
            "previous_state_available": settings.previous_target_state_available,
            "last_output_action": settings.last_output_action,
            "restore_first": True,
            "activation_progress_cleared": True,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
)

addon.unregister()
