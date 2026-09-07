from __future__ import annotations

import json
import os
from pathlib import Path

import bpy


if not bpy.app.background:
    raise RuntimeError("Real Action remap test refuses to run in Blender UI")
if os.environ.get("BAW_REAL_REMAP_ALLOW") != "read-only-background-test":
    raise RuntimeError("Set BAW_REAL_REMAP_ALLOW=read-only-background-test explicitly")

scene = bpy.context.scene
settings = scene.baw_auto_director
bridge = scene.ba_motion_bridge_settings
required_bounds = {(1, 150), (150, 224), (224, 293)}
owners = {}
for candidate in bpy.data.actions:
    if candidate.get("bam_role") != "RETARGET_OUTPUT" or candidate.get("baw_replaced_by"):
        continue
    owner_name = str(candidate.get("bam_target_object", "") or "")
    bounds = (
        int(round(float(candidate.get("bam_motion_frame_start", candidate.frame_range[0])))),
        int(round(float(candidate.get("bam_motion_frame_end", candidate.frame_range[1])))),
    )
    owners.setdefault(owner_name, set()).add(bounds)
target_name = next(name for name, bounds in owners.items() if required_bounds <= bounds)
target = bpy.data.objects[target_name]
owner_scene = next(candidate for candidate in bpy.data.scenes if target.name in candidate.objects)
if owner_scene != scene:
    bpy.context.window.scene = owner_scene
    scene = owner_scene
    settings = scene.baw_auto_director
    bridge = scene.ba_motion_bridge_settings
settings.target_rig = target
settings.reuse_target_rig = target
source = bridge.source_rig or bpy.data.objects.get("kimodo-soma-rp")
bridge.source_rig = source
bridge.target_rig = target
animation_data = target.animation_data
source_action_before = source.animation_data.action
source_use_nla_before = bool(source.animation_data.use_nla)


def matrix_error(left, right):
    return max(
        abs(float(left[row][column]) - float(right[row][column]))
        for row in range(4)
        for column in range(4)
    )


def clip_at(start, end):
    return next(
        action
        for action in bpy.data.actions
        if action.get("bam_role") == "RETARGET_OUTPUT"
        and action.get("bam_target_object") == target.name
        and int(round(float(action.frame_range[0]))) == start
        and int(round(float(action.frame_range[1]))) == end
        and not action.get("baw_replaced_by")
    )


def remap(action, expected_text):
    settings.remap_action = action
    if settings.remap_prompt_text is None or settings.remap_prompt_text.name != expected_text:
        raise AssertionError(
            f"Legacy Text association failed: {getattr(settings.remap_prompt_text, 'name', None)}"
        )
    old_name = action.name
    old_pointer = action.as_pointer()
    result = bpy.ops.baw.auto_remap_existing("EXEC_DEFAULT")
    if result != {"FINISHED"}:
        raise AssertionError(f"Remap failed: {result}; {settings.status_message}")
    replacement = settings.remap_action
    if replacement is None or replacement.as_pointer() == old_pointer:
        raise AssertionError("Remap did not create a replacement Action")
    if replacement.name != old_name:
        raise AssertionError(f"Replacement did not take the original name: {replacement.name}")
    if replacement.get("baw_prompt_text") != expected_text:
        raise AssertionError("Replacement lost its prompt Text association")
    source_action = bpy.data.actions.get(replacement.get("baw_source_action", ""))
    if source_action is None or not source_action.use_fake_user:
        raise AssertionError("Replacement lost its accepted source Action")
    if not action.name.startswith(old_name + "_BAW_替换前"):
        raise AssertionError(f"Old Action was not retained as a named backup: {action.name}")
    if action.get("baw_replaced_by") != replacement.name:
        raise AssertionError("Old Action backup does not point to its replacement")
    return replacement, action


active_third = animation_data.action
old_first = clip_at(-29, 150)
new_first, backup_first = remap(old_first, "第一段")
if animation_data.action != active_third or not animation_data.use_nla:
    raise AssertionError("Remapping the preroll Clip changed the active later Clip")
if int(round(float(new_first.frame_range[0]))) != -29:
    raise AssertionError("First Clip remap did not preserve its negative transition margin")

old_second = clip_at(150, 224)
new_second, backup_second = remap(old_second, "第二段")
if animation_data.action != active_third or not animation_data.use_nla:
    raise AssertionError("Remapping an NLA Clip changed the active later Clip")
if not any(
    strip.action == new_second
    for track in animation_data.nla_tracks
    for strip in track.strips
):
    raise AssertionError("Second Clip replacement was not installed into its NLA strip")

new_third, backup_third = remap(active_third, "第三段")
if animation_data.action != new_third or not animation_data.use_nla:
    raise AssertionError("Remapping the active Clip did not activate its replacement")
if source.animation_data.action != source_action_before or bool(source.animation_data.use_nla) != source_use_nla_before:
    raise AssertionError("Accepted source rig state was not restored after remap")

clips = [
    new_first,
    new_second,
    new_third,
]
seam_errors = []
for previous, following, seam in zip(clips, clips[1:], (150, 224)):
    animation_data.use_nla = False
    animation_data.action = previous
    scene.frame_set(seam)
    bpy.context.view_layer.update()
    previous_pose = {
        name: target.pose.bones[name].matrix.copy()
        for name in ("センター", "グルーブ", "下半身")
    }
    animation_data.action = following
    scene.frame_set(seam)
    bpy.context.view_layer.update()
    errors = {
        name: matrix_error(target.pose.bones[name].matrix, previous_pose[name])
        for name in previous_pose
    }
    if max(errors.values()) >= 2e-4:
        raise AssertionError(f"Replacement continuity failed at {seam}: {errors}")
    seam_errors.append({"seam": seam, "errors": errors})

animation_data.action = new_third
animation_data.use_nla = True
output_dir = Path(os.environ["BAW_REAL_REMAP_OUTPUT"])
output_dir.mkdir(parents=True, exist_ok=True)
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 640
scene.render.resolution_y = 360
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
for frame in (149, 150, 223, 224):
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    scene.render.filepath = str(output_dir / f"remapped_{frame:04d}.png")
    bpy.ops.render.render(write_still=True)

print("BAW_REAL_ACTION_REMAP=" + json.dumps({
    "status": "PASS",
    "file": bpy.data.filepath,
    "second": new_second.name,
    "second_prompt": new_second.get("baw_prompt_text"),
    "second_source": new_second.get("baw_source_action"),
    "third": new_third.name,
    "third_prompt": new_third.get("baw_prompt_text"),
    "third_source": new_third.get("baw_source_action"),
    "backups": [backup_first.name, backup_second.name, backup_third.name],
    "seam_errors": seam_errors,
    "saved": False,
    "cloud_generation_invoked": False,
}, ensure_ascii=False))
