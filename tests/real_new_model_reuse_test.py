from __future__ import annotations

import json
import os

import bpy


if not bpy.app.background:
    raise RuntimeError("Real new-model reuse test refuses to run in Blender UI")
if os.environ.get("BAW_REAL_REUSE_ALLOW") != "read-only-background-test":
    raise RuntimeError("Set BAW_REAL_REUSE_ALLOW=read-only-background-test explicitly")

scene = bpy.context.scene
settings = scene.baw_auto_director
bridge = scene.ba_motion_bridge_settings


def clip_bounds(action):
    start = int(round(float(action.get("bam_motion_frame_start", action.frame_range[0]))))
    end = int(round(float(action.get("bam_motion_frame_end", action.frame_range[1]))))
    return start, end


reusable_actions = [
    action
    for action in bpy.data.actions
    if action.get("bam_role") == "RETARGET_OUTPUT"
    and not action.get("baw_replaced_by")
]
actions_by_owner = {}
for action in reusable_actions:
    actions_by_owner.setdefault(str(action.get("bam_target_object", "") or ""), []).append(action)
source_actions = max(actions_by_owner.values(), key=len, default=[])
source_actions.sort(key=lambda action: (*clip_bounds(action), action.name))
if len(source_actions) < 3:
    raise AssertionError(f"Expected one model with at least three reusable Actions, got {len(source_actions)}")
source_actions = source_actions[:3]
source_link_props = [
    {
        "name": action.name,
        "bounds": clip_bounds(action),
        "prompt_text": action.get("baw_prompt_text"),
        "prompt": action.get("baw_prompt"),
        "source_action": action.get("baw_source_action"),
    }
    for action in source_actions
]
old_target_name = str(source_actions[0].get("bam_target_object", "") or "")
old_target = bpy.data.objects.get(old_target_name)
if old_target is None:
    raise AssertionError(f"Old target model is missing: {old_target_name}")
if any(str(action.get("bam_target_object", "") or "") != old_target_name for action in source_actions):
    raise AssertionError("The first three reusable Actions do not belong to one old model")

old_animation = old_target.animation_data
old_active = old_animation.action
old_use_nla = bool(old_animation.use_nla)
old_strips = [
    (strip.as_pointer(), strip.action.as_pointer() if strip.action else 0)
    for track in old_animation.nla_tracks
    for strip in track.strips
]
source_rig = bridge.source_rig or bpy.data.objects.get("kimodo-soma-rp")
source_active = source_rig.animation_data.action
source_use_nla = bool(source_rig.animation_data.use_nla)

new_target = old_target.copy()
new_target.data = old_target.data.copy()
new_target.name = "BAW_Reuse_New_Model_Test"
new_target.data.name = "BAW_Reuse_New_Model_Test_Data"
new_target.animation_data_clear()
scene.collection.objects.link(new_target)

preflight_links = []
for action in source_actions:
    settings.remap_action = action
    preflight_links.append(
        settings.remap_prompt_text.name if settings.remap_prompt_text is not None else None
    )
settings.remap_action = source_actions[1]
settings.reuse_target_rig = new_target
result = bpy.ops.baw.auto_import_all_existing("EXEC_DEFAULT")
if result != {"FINISHED"}:
    raise AssertionError(f"Batch reuse failed: {result}; {settings.status_message}")

new_animation = new_target.animation_data
if new_animation is None or new_animation.action is None:
    raise AssertionError("New model did not receive an active Action")
imported = {
    action
    for action in [new_animation.action]
    + [strip.action for track in new_animation.nla_tracks for strip in track.strips]
    if action is not None
}
if len(imported) != 3:
    raise AssertionError(f"Expected three imported Actions on the new model, got {len(imported)}")
imported = sorted(imported, key=lambda action: (*clip_bounds(action), action.name))
if [clip_bounds(action) for action in imported] != [(1, 150), (150, 224), (224, 293)]:
    raise AssertionError(f"Imported Clip ranges are wrong: {[clip_bounds(action) for action in imported]}")
if int(round(float(imported[0].frame_range[0]))) != -29:
    raise AssertionError("The first imported Clip lost its negative transition margin")
prompt_links = [action.get("baw_prompt_text") for action in imported]
if prompt_links != ["第一段", "第二段", "第三段"]:
    raise AssertionError(
        f"Imported Actions lost their linked prompt Text blocks: {prompt_links}; "
        f"preflight={preflight_links}; source_props={source_link_props}"
    )
if any(action.get("baw_reused_from_target") != old_target_name for action in imported):
    raise AssertionError("Imported Actions do not record the old source model")
batch_ids = {str(action.get("baw_reuse_batch_id", "")) for action in imported}
if len(batch_ids) != 1 or not next(iter(batch_ids)):
    raise AssertionError("Imported Actions do not share one reuse batch id")

if old_animation.action != old_active or bool(old_animation.use_nla) != old_use_nla:
    raise AssertionError("Batch import changed the old model's active animation state")
if old_strips != [
    (strip.as_pointer(), strip.action.as_pointer() if strip.action else 0)
    for track in old_animation.nla_tracks
    for strip in track.strips
]:
    raise AssertionError("Batch import changed the old model's NLA strips")
if source_rig.animation_data.action != source_active or bool(source_rig.animation_data.use_nla) != source_use_nla:
    raise AssertionError("Batch import did not restore the accepted source rig state")

single_target = old_target.copy()
single_target.data = old_target.data.copy()
single_target.name = "BAW_Reuse_One_Clip_Test"
single_target.data.name = "BAW_Reuse_One_Clip_Test_Data"
single_target.animation_data_clear()
scene.collection.objects.link(single_target)
settings.remap_action = source_actions[1]
settings.reuse_target_rig = single_target
# Reproduce the UI race: after the button captured Clip 02, the playhead/current
# context moves to Clip 03 and the Scene-level selector follows it. The operator
# must still import the Action explicitly captured by the clicked button.
scene.frame_set(260)
settings.remap_action = source_actions[2]
single_result = bpy.ops.baw.auto_import_existing(
    "EXEC_DEFAULT",
    action_name=source_actions[1].name,
)
if single_result != {"FINISHED"}:
    raise AssertionError(f"Single-Clip reuse failed: {single_result}; {settings.status_message}")
single_action = single_target.animation_data.action
if single_action is None or clip_bounds(single_action) != (150, 224):
    raise AssertionError("Single-Clip reuse did not activate the requested frame range")
if single_action.get("baw_prompt_text") != "第二段":
    raise AssertionError("Single-Clip reuse lost its prompt association")


def matrix_error(left, right):
    return max(
        abs(float(left[row][column]) - float(right[row][column]))
        for row in range(4)
        for column in range(4)
    )


seam_errors = []
for previous, following, seam in zip(imported, imported[1:], (150, 224)):
    new_animation.use_nla = False
    new_animation.action = previous
    scene.frame_set(seam)
    bpy.context.view_layer.update()
    previous_pose = {
        name: new_target.pose.bones[name].matrix.copy()
        for name in ("センター", "グルーブ", "下半身")
    }
    new_animation.action = following
    scene.frame_set(seam)
    bpy.context.view_layer.update()
    errors = {
        name: matrix_error(new_target.pose.bones[name].matrix, previous_pose[name])
        for name in previous_pose
    }
    if max(errors.values()) >= 2e-4:
        raise AssertionError(f"New-model continuity failed at {seam}: {errors}")
    seam_errors.append({"seam": seam, "errors": errors})

new_animation.action = imported[-1]
new_animation.use_nla = True
print("BAW_REAL_NEW_MODEL_REUSE=" + json.dumps({
    "status": "PASS",
    "file": bpy.data.filepath,
    "old_target": old_target.name,
    "new_target": new_target.name,
    "clips": [
        {
            "action": action.name,
            "bounds": clip_bounds(action),
            "prompt_text": action.get("baw_prompt_text"),
            "source_action": action.get("baw_source_action"),
        }
        for action in imported
    ],
    "first_preroll": int(round(float(imported[0].frame_range[0]))),
    "nla_strips": sum(len(track.strips) for track in new_animation.nla_tracks),
    "single_clip": {
        "target": single_target.name,
        "action": single_action.name,
        "bounds": clip_bounds(single_action),
        "prompt_text": single_action.get("baw_prompt_text"),
    },
    "seam_errors": seam_errors,
    "old_model_unchanged": True,
    "saved": False,
    "cloud_generation_invoked": False,
}, ensure_ascii=False))
