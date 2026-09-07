from __future__ import annotations

import json
import importlib
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import bpy
from mathutils import Quaternion, Vector


WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.environ.get("BAW_AUTO_IMPORT_ROOT", str(WORKSPACE / "extension")))

addon = importlib.import_module(os.environ.get("BAW_AUTO_ADDON_MODULE", "ba_animation_workflow"))
bridge_addon = importlib.import_module(
    os.environ.get("BAW_BRIDGE_ADDON_MODULE", "ba_motion_bridge")
)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class LayoutProbe:
    def __init__(self, events):
        self.events = events
        self.alert = False
        self.enabled = True
        self.scale_y = 1.0

    def box(self):
        return LayoutProbe(self.events)

    def row(self, **_kwargs):
        return LayoutProbe(self.events)

    def column(self, **_kwargs):
        return LayoutProbe(self.events)

    def label(self, *, text="", icon="NONE", **_kwargs):
        self.events.append(("label", text, icon))

    def prop(self, _data, name, **_kwargs):
        self.events.append(("prop", name))

    def operator(self, identifier, *, text="", icon="NONE", **_kwargs):
        self.events.append(("operator", identifier, text, icon))
        return SimpleNamespace()

    def progress(self, *, factor=0.0, type="BAR", text="", **_kwargs):
        self.events.append(("progress", factor, type, text))

    def template_ID(self, _data, name, **kwargs):
        self.events.append(("template_ID", name, kwargs))


def main() -> None:
    if not bpy.app.background:
        raise RuntimeError("Auto Director smoke test must run in Blender background mode")

    for obj in tuple(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    if not hasattr(bpy.types.Scene, "ba_motion_bridge_settings"):
        bridge_addon.register()
    if not hasattr(bpy.types.Scene, "baw_auto_director"):
        addon.register()
    scene = bpy.context.scene

    foreign_world = bpy.data.worlds.new("UserWorld")
    foreign_world.use_nodes = True
    foreign_background = foreign_world.node_tree.nodes.get("Background") or foreign_world.node_tree.nodes.new("ShaderNodeBackground")
    foreign_background.inputs["Strength"].default_value = 0.73
    scene.world = foreign_world

    camera_data = bpy.data.cameras.new("UserCameraData")
    camera_data.lens = 31.0
    foreign_camera = bpy.data.objects.new("UserCamera", camera_data)
    scene.collection.objects.link(foreign_camera)
    scene.camera = foreign_camera

    armature_data = bpy.data.armatures.new("UserRigData")
    armature = bpy.data.objects.new("UserRig", armature_data)
    scene.collection.objects.link(armature)
    bpy.context.view_layer.objects.active = armature
    armature.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    edit_bone = armature_data.edit_bones.new("root")
    edit_bone.head = (0.0, 0.0, 0.0)
    edit_bone.tail = (0.0, 0.0, 1.0)
    groove_bone = armature_data.edit_bones.new("groove")
    groove_bone.head = (0.0, 0.0, 0.2)
    groove_bone.tail = (0.0, 0.0, 0.7)
    groove_bone.parent = edit_bone
    secondary_bone = armature_data.edit_bones.new("skirt")
    secondary_bone.head = (0.0, 0.0, 0.5)
    secondary_bone.tail = (0.0, 0.4, 0.5)
    body_control_bone = armature_data.edit_bones.new("body_ctrl")
    body_control_bone.head = (0.0, 0.0, 0.7)
    body_control_bone.tail = (0.0, 0.0, 1.2)
    body_control_bone.parent = edit_bone
    auxiliary_bone = armature_data.edit_bones.new("ik_aux")
    auxiliary_bone.head = (0.0, 0.0, 0.25)
    auxiliary_bone.tail = (0.3, 0.0, 0.25)
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.mesh.primitive_cube_add(location=(0.0, 0.0, 1.0), scale=(0.3, 0.2, 1.0))
    body = bpy.context.object
    body.name = "UserBody"
    body.parent = armature
    bpy.context.view_layer.objects.active = armature
    armature.select_set(True)

    foreign_plan = bpy.data.texts.new("BAW_自动导演方案")
    foreign_plan.write("user-owned")

    settings = scene.baw_auto_director
    settings.target_rig = armature
    settings.creative_prompt = "教室里角色向前走两步；然后温暖地挥手"
    settings.total_frames = 120
    scene.render.fps = 30
    scene.render.fps_base = 1.0

    check(bpy.ops.baw.auto_compile_plan() == {"FINISHED"}, "Plan compilation failed")
    plan = json.loads(settings.plan_json)
    check(plan["schema"] == 4, "Unexpected plan schema")
    check(plan["environment"] == "CLASSROOM", "Classroom intent was not detected")
    check(plan["lighting"] == "WARM", "Warm lighting intent was not detected")
    check((plan["frame_start"], plan["frame_end"], plan["frame_count"]) == (1, 120, 120), "Panel total frames were not applied")
    check(len(plan["prompt_blocks"]) == 1, "Single mode created more than one prompt block")
    check(plan["prompt_blocks"][0]["prompt"] == settings.creative_prompt, "Single prompt content changed")
    check(plan["timing_sources"] == {"fps": "SCENE", "frames": "PANEL", "blocks": "SINGLE"}, "Single-mode timing sources are wrong")
    check(plan["prompt_source"] == "LEGACY", "Legacy prompt fallback source was not recorded")
    check(plan["bridge"] == {"motion_space": "TARGET_PLACEMENT", "end_effector_guard": True, "end_effector_guard_strength": 1.0}, "PMB 0.9.1 defaults were not recorded in the plan")
    check(foreign_plan.as_string() == "user-owned", "Foreign plan text was overwritten")
    check(settings.plan_text_name != foreign_plan.name, "Foreign plan text was claimed")

    auto_director = importlib.import_module(addon.__name__ + ".auto_director")
    bridge = scene.ba_motion_bridge_settings
    previous_target_data = bpy.data.armatures.new("PreviousAutoTargetData")
    previous_target = bpy.data.objects.new("PreviousAutoTarget", previous_target_data)
    scene.collection.objects.link(previous_target)
    previous_output = bpy.data.actions.new("PreviousAutoTargetOutput")
    previous_output.use_fake_user = True
    bridge.target_rig = previous_target
    bridge.previous_target_state_available = True
    bridge.previous_target_rig = previous_target
    bridge.previous_target_action = previous_output
    bridge.previous_target_action_name = previous_output.name
    bridge.previous_target_action_fake_user = False
    bridge.constraint_snapshot_json = "[]"
    bridge.constraint_snapshot_target = previous_target.name
    bridge.constraint_snapshot_target_rig = previous_target
    bridge.target_switch_snapshot_json = "[]"
    bridge.target_switch_snapshot_target = previous_target.name
    bridge.physics_cache_snapshot_json = '{"present":false}'
    bridge.timeline_snapshot_json = '{"frame_start":1}'
    switched_from = auto_director._resolve_auto_target_switch(
        bpy.context,
        bridge,
        armature,
    )
    check(switched_from == previous_target.name, "Auto workflow did not identify the previous target")
    check(bridge.target_rig == armature, "Auto workflow lost the newly selected target")
    check(not bridge.previous_target_state_available, "Auto workflow did not release the old target recovery slot")
    check(not bridge.constraint_snapshot_json, "Auto workflow left the old target constraint snapshot active")
    check(not bridge.timeline_snapshot_json, "Auto workflow left the old target timeline snapshot active")
    check(not previous_output.use_fake_user, "Auto target switch did not normalize the old baseline Action")
    check(not settings.build_set, "Automatic set building must default to off")
    check(not settings.build_lighting, "Automatic lighting must default to off")
    check(not settings.build_camera, "Automatic camera composition must default to off")
    check(settings.preroll_margin == 60, "Unexpected default preroll margin")
    check(not hasattr(settings, "preroll_transition_frames"), "Redundant preroll transition field still exists")
    settings.creative_prompt = "THIS LEGACY VALUE MUST NOT BE USED"
    multiline_text = bpy.data.texts.new("BAW_Multiline_Test")
    multiline_text.write("""30 FPS
## Clip 01 — multiline
timeline:
  - frames: 1-60
    prompt: \"A person raises their right hand.\"
  - frames: 61-90
    prompt: \"The person settles into a relaxed pose.\"
pose_anchors:
  - frame: 90
    prompt: \"A relaxed ending pose.\"
""")
    settings.prompt_text = multiline_text
    settings.total_frames = 90
    multiline_plan = auto_director.compile_plan(settings)
    check(multiline_plan["prompt_source"] == "TEXT", "Multiline Text source was not preferred")
    check(multiline_plan["frame_count"] == 90, "Panel total frames were not used for multiline text")
    check(len(multiline_plan["prompt_blocks"]) == 1, "Multiline text was split into multiple prompt blocks")
    check(multiline_plan["prompt_blocks"][0]["prompt"] == multiline_text.as_string().strip(), "Multiline text was not kept as one literal segment")
    check(multiline_plan["pose_anchors"] == [], "Pose Anchors were still parsed from prompt text")
    settings.prompt_text = None
    settings.creative_prompt = "旧提示第一行\n旧提示第二行"
    check(bpy.ops.baw.auto_prompt_new() == {"FINISHED"}, "Multiline Text creation failed")
    migrated_text = settings.prompt_text
    check(migrated_text is not None and migrated_text.as_string() == settings.creative_prompt, "Legacy prompt was not migrated exactly")
    check(migrated_text.use_fake_user, "Multiline prompt Text is not protected for .blend persistence")
    check(bpy.ops.baw.auto_prompt_unlink() == {"FINISHED"}, "Multiline Text unlink failed")
    check(settings.prompt_text is None and migrated_text.name in bpy.data.texts, "Unlink deleted user prompt data")
    structured_prompt = """60 FPS
## Clip — structure must remain literal
timeline:
  - frames: 1-30
    prompt: \"A person stirs slowly.\"
  - frames: 31-60
    prompt: \"The person settles into a quiet stop.\"
pose_anchors:
  - frame: 60
    prompt: \"A person holds a relaxed ending pose.\"
"""
    settings.creative_prompt = structured_prompt
    settings.total_frames = 75
    settings.root_motion = "IN_PLACE"
    scene.render.fps = 24
    structured = auto_director.compile_plan(settings, placement_frame=100)
    check(structured["fps"] == 24, "Scene FPS was not used")
    check((structured["frame_start"], structured["frame_end"]) == (100, 174), "Current-frame placement or panel total is wrong")
    check(abs(structured["duration_seconds"] - 75 / 24) < 1e-6, "Duration is not derived from panel frames and scene FPS")
    check(len(structured["generation_batches"]) == 1, "A single Clip did not compile to one batch")
    check([(item["frame_start"], item["frame_end"]) for item in structured["prompt_blocks"]] == [(100, 174)], "Single prompt range is wrong")
    check(structured["prompt_blocks"][0]["prompt"] == structured_prompt.strip(), "Structured directives were not kept literal")
    check(structured["pose_anchors"] == [], "Structured Pose Anchors were unexpectedly parsed")
    check(structured["generation_batches"][0]["root_motion"] == "IN_PLACE", "Panel root motion was not used")
    check(structured["generation_batches"][0]["authored_frame_start"] == 1, "Authored Clip range was not preserved")
    settings.creative_prompt = "A" * 1001
    try:
        auto_director.compile_plan(settings)
    except ValueError as exc:
        check("1000" in str(exc), "Overlong single prompt returned the wrong error")
    else:
        raise AssertionError("Overlong single prompt was accepted")
    settings.creative_prompt = structured_prompt

    preroll = auto_director._choose_start_behavior(False, 100, 1, 60)
    check(preroll == {"mode": "PREROLL", "motion_start": 100, "preroll_start": 40, "had_existing_motion": False}, "No-motion preroll decision is wrong")
    continuity = auto_director._choose_start_behavior(True, 100, 1, 60)
    check(continuity["mode"] == "CURRENT_POSE" and continuity["preroll_start"] == 100, "Existing-motion continuity decision is wrong")
    timeline_start = auto_director._choose_start_behavior(True, 1, 1, 60)
    check(timeline_start["mode"] == "PREROLL" and timeline_start["preroll_start"] == -59, "Timeline-start negative preroll decision is wrong")

    pose_bone = armature.pose.bones["root"]
    groove_control = armature.pose.bones["groove"]
    skirt_bone = armature.pose.bones["skirt"]
    body_control = armature.pose.bones["body_ctrl"]
    animation_data = armature.animation_data_create()
    animation_data.action = None
    pose_bone.rotation_mode = "QUATERNION"
    groove_control.rotation_mode = "QUATERNION"
    skirt_bone.rotation_mode = "QUATERNION"
    body_control.rotation_mode = "QUATERNION"
    pose_bone.location.x = 0.0
    pose_bone.rotation_quaternion = Quaternion()
    pose_bone.keyframe_insert("location", frame=40, group=pose_bone.name)
    pose_bone.keyframe_insert("rotation_quaternion", frame=40, group=pose_bone.name)
    groove_control.location.x = 0.0
    groove_control.keyframe_insert("location", frame=40, group=groove_control.name)
    skirt_bone.rotation_quaternion = Quaternion()
    skirt_bone.keyframe_insert("rotation_quaternion", frame=40, group=skirt_bone.name)
    body_control.rotation_quaternion = Quaternion()
    body_control.keyframe_insert("rotation_quaternion", frame=40, group=body_control.name)
    pose_bone.location.x = 2.0
    # The upright test bone's local Y is world Z (horizontal facing).
    pose_bone.rotation_quaternion = Quaternion((0.0, 1.0, 0.0), 1.5707963267948966)
    pose_bone.keyframe_insert("location", frame=100, group=pose_bone.name)
    pose_bone.keyframe_insert("rotation_quaternion", frame=100, group=pose_bone.name)
    groove_control.location.x = 0.25
    groove_control.keyframe_insert("location", frame=100, group=groove_control.name)
    skirt_bone.rotation_quaternion = Quaternion((1.0, 0.0, 0.0), 0.7853981633974483)
    skirt_bone.keyframe_insert("rotation_quaternion", frame=100, group=skirt_bone.name)
    body_control.rotation_quaternion = Quaternion((0.0, 1.0, 0.0), 1.5707963267948966)
    body_control.keyframe_insert("rotation_quaternion", frame=100, group=body_control.name)
    previous_action = animation_data.action
    previous_action.name = "Previous_Clip"
    previous_action.use_frame_range = True
    previous_action.frame_start = 100
    previous_action.frame_end = 100
    previous_action["bam_preroll_frame_start"] = 40
    previous_action["bam_motion_frame_start"] = 100
    previous_action["bam_motion_frame_end"] = 100
    previous_key_count = sum(
        len(curve.keyframe_points)
        for curve in auto_director._iter_action_fcurves(previous_action)
    )
    pose_target = bpy.data.objects.new("VisiblePoseTarget", None)
    pose_target.location.x = 5.0
    scene.collection.objects.link(pose_target)
    visible_constraint = pose_bone.constraints.new("COPY_LOCATION")
    visible_constraint.name = "VisiblePoseConstraint"
    visible_constraint.target = pose_target
    auxiliary_pose_bone = armature.pose.bones["ik_aux"]
    auxiliary_constraint = auxiliary_pose_bone.constraints.new("COPY_LOCATION")
    auxiliary_constraint.name = "AuxiliaryVisibleConstraint"
    auxiliary_constraint.target = pose_target
    scene.frame_set(100)
    bpy.context.view_layer.update()
    check(abs(pose_bone.matrix.translation.x - 5.0) < 1e-6, "Constraint test did not create a distinct visible pose")
    check(auto_director._target_has_motion(armature), "Target action was not detected as existing motion")
    auto_director._prepare_start_behavior(bpy.context, settings, structured)
    check(settings.start_behavior == "CURRENT_POSE", "Existing action did not select continuity mode")
    check(settings.previous_clip_action == previous_action, "Previous active Action was not captured")
    captured_pose = settings.continuity_pose_json
    captured_root = next(row for row in json.loads(captured_pose) if row["bone"] == "root")
    check(abs(captured_root["matrix"][0][3] - 5.0) < 1e-6, "Visible evaluated pose was not captured")
    visible_constraint.mute = True
    auxiliary_constraint.mute = True
    auxiliary_basis_before = auxiliary_pose_bone.matrix_basis.copy()
    animation_data.action = None
    pose_bone.location.x = -1.0
    pose_bone.rotation_quaternion = Quaternion()
    pose_bone.keyframe_insert("location", frame=100, group=pose_bone.name)
    pose_bone.keyframe_insert("rotation_quaternion", frame=100, group=pose_bone.name)
    groove_control.location.x = -0.4
    groove_control.keyframe_insert("location", frame=100, group=groove_control.name)
    pose_bone.location.x = 1.0
    pose_bone.rotation_quaternion = Quaternion((0.0, 1.0, 0.0), 0.7853981633974483)
    pose_bone.keyframe_insert("location", frame=174, group=pose_bone.name)
    pose_bone.keyframe_insert("rotation_quaternion", frame=174, group=pose_bone.name)
    groove_control.location.x = 0.6
    groove_control.keyframe_insert("location", frame=174, group=groove_control.name)
    body_control.rotation_quaternion = Quaternion()
    body_control.keyframe_insert("rotation_quaternion", frame=100, group=body_control.name)
    body_control.rotation_quaternion = Quaternion((0.0, 1.0, 0.0), 0.7853981633974483)
    body_control.keyframe_insert("rotation_quaternion", frame=174, group=body_control.name)
    output_action = animation_data.action
    scene.frame_set(106)
    bpy.context.view_layer.update()
    raw_body_release = body_control.matrix_basis.copy()
    check(auto_director._preserve_previous_clip(settings, output_action) == 1, "Previous Clip was not moved into NLA")
    check(auto_director._apply_continuity_pose(scene, settings, output_action) == 3, "Continuity pose was not keyed")
    check(
        all(
            abs(auxiliary_pose_bone.matrix_basis[row][column] - auxiliary_basis_before[row][column]) < 1e-7
            for row in range(4)
            for column in range(4)
        ),
        "Continuity mutated an auxiliary bone not owned by the new Action",
    )
    previous_strips = [
        strip
        for track in animation_data.nla_tracks
        for strip in track.strips
        if strip.action == previous_action
    ]
    check(animation_data.action == output_action and animation_data.use_nla, "New Action and previous NLA are not both active")
    check(len(previous_strips) == 1, "Previous Clip NLA strip is missing or duplicated")
    check(previous_strips[0].frame_start == 40, "Previous Clip preroll was not preserved in NLA")
    check(previous_strips[0].action_frame_start == 40, "Previous Clip NLA action range omitted preroll")
    check(previous_strips[0].frame_end == 100, "Previous Clip was not trimmed at the new Clip boundary")
    check(previous_strips[0].extrapolation == "NOTHING", "Previous Clip still leaks held channels into the new Clip")
    previous_strips[0].extrapolation = "HOLD_FORWARD"
    check(auto_director._preserve_previous_clip(settings, output_action) == 0, "Existing previous Clip NLA was duplicated")
    check(previous_strips[0].extrapolation == "NOTHING", "Legacy BA continuity strip was not migrated")
    check(previous_action.frame_start == 40, "Previous Action custom range still hides preroll keys")
    check(output_action.use_frame_range and output_action.frame_start == 100, "New Action is active before the Clip start")
    check(animation_data.action_extrapolation == "NOTHING", "New Action still masks the previous Clip before its first key")
    check(sum(len(curve.keyframe_points) for curve in auto_director._iter_action_fcurves(previous_action)) == previous_key_count, "Previous Action keys were modified")
    scene.frame_set(50)
    check(0.0 < pose_bone.location.x < 2.0, "Previous Clip is not evaluated before the new Clip boundary")
    check(abs(skirt_bone.rotation_quaternion.x) > 1e-4, "Previous Clip lost a channel before its boundary")
    output_paths = {curve.data_path for curve in auto_director._iter_action_fcurves(output_action)}
    check(all('pose.bones["skirt"]' not in path for path in output_paths), "Continuity keyed an ungenerated secondary bone")
    check(output_paths == {
        'pose.bones["root"].location',
        'pose.bones["root"].rotation_quaternion',
        'pose.bones["groove"].location',
        'pose.bones["body_ctrl"].rotation_quaternion',
    }, "Continuity changed the generated Action channel schema")
    scene.frame_set(100)
    bpy.context.view_layer.update()
    check(abs(pose_bone.matrix.translation.x - 5.0) < 1e-6, "Visible current pose was not restored at the new Clip first frame")
    check(
        abs(groove_control.location.x - 0.25) < 1e-6,
        "Child root-motion bone double-counted its parent at the Clip seam",
    )
    scene.frame_set(174)
    bpy.context.view_layer.update()
    check(
        abs(pose_bone.matrix.translation.x - 5.0) < 1e-5
        and abs((pose_bone.matrix.translation - Vector((5.0, 0.0, 0.0))).length - 2.0) < 1e-5,
        f"New Clip displacement was not rebased into the current facing: {tuple(pose_bone.matrix.translation)}",
    )
    end_rotation = pose_bone.matrix_basis.to_quaternion()
    expected_rotation = Quaternion((0.0, 1.0, 0.0), 2.356194490192345)
    check(abs(end_rotation.dot(expected_rotation)) > 1.0 - 1e-5, "New Clip was not rebased onto the current rotation")
    check(
        abs(body_control.matrix_basis.to_quaternion().angle - 0.7853981633974483) < 1e-5,
        "Body pose delta was incorrectly carried through the whole Clip",
    )
    scene.frame_set(100)
    bpy.context.view_layer.update()
    check(
        abs(body_control.matrix_basis.to_quaternion().angle - 1.5707963267948966) < 1e-5,
        "Body did not start from the captured previous pose",
    )
    scene.frame_set(106)
    bpy.context.view_layer.update()
    check(
        (body_control.matrix_basis.to_quaternion().rotation_difference(
            raw_body_release.to_quaternion()
        ).angle < 1e-5),
        "Body did not return to the raw generated motion after the transition",
    )
    scene.frame_set(151)
    bpy.context.view_layer.update()
    check(abs(skirt_bone.rotation_quaternion.x) < 1e-5, "An old Clip channel leaked into the new Clip")

    source_holder = bpy.data.objects.new("AcceptedSourceRig", None)
    scene.collection.objects.link(source_holder)
    source_holder.location.x = 0.0
    source_holder.keyframe_insert("location", frame=100)
    source_holder.location.x = 1.0
    source_holder.keyframe_insert("location", frame=174)
    source_action = source_holder.animation_data.action
    source_action.name = "Proscenium_Motion: A person raises one hand."
    clip_prompt = bpy.data.texts.new("Clip 02 Prompt")
    clip_prompt.write("A person raises one hand.")
    output_action["bam_role"] = "RETARGET_OUTPUT"
    output_action["bam_source_object"] = source_holder.name
    output_action["bam_target_object"] = armature.name
    linked_source, linked_text = auto_director._resolve_action_link(
        scene, settings, output_action, persist=True
    )
    check(linked_source == source_action, "Legacy target Action was not matched to its accepted source Action")
    check(linked_text == clip_prompt, "Legacy target Action was not matched to its prompt Text")
    check(source_action.use_fake_user and clip_prompt.use_fake_user, "Linked source data was not protected for file persistence")
    settings.remap_action = output_action
    check(settings.remap_prompt_text == clip_prompt, "Selecting a generated Action did not restore its linked prompt Text")

    fourth_text = bpy.data.texts.new("第四段")
    fourth_text.write("The person becomes still, turns the head over the right shoulder.")
    fourth_source = bpy.data.actions.new(
        "Proscenium_Motion: The person becomes still, turns the head over the right shoulder."
    )
    wrong_source = bpy.data.actions.new("Proscenium_Motion: A person draws both hands inward.")
    wrong_output = bpy.data.actions.new("BAW_Wrong_Fourth_Output")
    wrong_output["bam_role"] = "RETARGET_OUTPUT"
    wrong_output["bam_target_object"] = armature.name
    wrong_output["baw_source_action"] = wrong_source.name
    wrong_output["baw_prompt_text"] = fourth_text.name
    wrong_output["baw_prompt"] = fourth_text.as_string()
    polluted_clip_id = "legacy-polluted-fourth-link"
    fourth_text["baw_clip_id"] = polluted_clip_id
    fourth_text["baw_current_action"] = wrong_output.name
    fourth_text["baw_source_action"] = wrong_source.name
    wrong_output["baw_clip_id"] = polluted_clip_id
    wrong_source["baw_clip_id"] = polluted_clip_id
    wrong_source["baw_prompt"] = fourth_text.as_string()
    settings.remap_prompt_text = fourth_text
    check(
        settings.remap_action == fourth_source,
        "Text-first recovery trusted a stale label instead of the matching accepted source Action",
    )
    settings.remap_prompt_syncing = True
    try:
        settings.remap_prompt_text = fourth_text
        settings.remap_action = wrong_output
    finally:
        settings.remap_prompt_syncing = False
    requested = auto_director._requested_reuse_action(settings, wrong_output.name)
    check(
        requested == fourth_source,
        "Import execution trusted the stale button Action instead of re-resolving the selected Text",
    )
    settings.remap_prompt_syncing = True
    try:
        settings.remap_action = wrong_output
    finally:
        settings.remap_prompt_syncing = False
    auto_director._sync_reuse_selection(scene)
    check(
        settings.remap_action == fourth_source,
        "File-load synchronization did not repair a stale Text/Action selection",
    )
    safe_fourth = bpy.data.actions.new("BAW_Fourth_Safe_Replacement")
    safe_fourth["bam_role"] = "RETARGET_OUTPUT"
    safe_fourth["bam_target_object"] = armature.name
    safe_fourth["baw_source_action"] = fourth_source.name
    animation_data.action = wrong_output
    auto_director._persist_text_action_link(
        fourth_text,
        safe_fourth,
        fourth_source,
        replace=True,
    )
    check(
        animation_data.action == wrong_output and not wrong_output.get("baw_replaced_by"),
        "A polluted Text map allowed a different source Action to be overwritten",
    )
    animation_data.action = None
    safe_fourth.use_fake_user = False
    bpy.data.actions.remove(safe_fourth)

    old_fourth = bpy.data.actions.new("BAW_Fourth_Old")
    old_fourth["bam_role"] = "RETARGET_OUTPUT"
    old_fourth["bam_target_object"] = armature.name
    old_fourth["baw_source_action"] = fourth_source.name
    auto_director._persist_text_action_link(
        fourth_text,
        old_fourth,
        fourth_source,
        replace=False,
    )
    animation_data.action = old_fourth
    new_fourth = bpy.data.actions.new("BAW_Fourth_New")
    new_fourth["bam_role"] = "RETARGET_OUTPUT"
    new_fourth["bam_target_object"] = armature.name
    new_fourth["baw_source_action"] = fourth_source.name
    old_fourth_name = old_fourth.name
    auto_director._persist_text_action_link(
        fourth_text,
        new_fourth,
        fourth_source,
        replace=True,
    )
    check(animation_data.action == new_fourth, "New Action did not replace the old Action reference for the same Text")
    check(fourth_text.get("baw_current_action") == new_fourth.name, "Text does not own its current Action")
    check(fourth_text.get("baw_source_action") == fourth_source.name, "Text does not own its accepted source Action")
    check(new_fourth.get("baw_clip_id") == fourth_text.get("baw_clip_id"), "Text/Action stable Clip IDs differ")
    check(
        json.loads(fourth_text.get("baw_action_links_json", "{}"))[armature.name] == new_fourth.name,
        "Per-target Text/Action link did not move to the replacement",
    )
    check(
        bpy.data.actions.get(old_fourth_name) is None
        or bpy.data.actions.get(old_fourth_name).get("baw_replaced_by") == new_fourth.name,
        "Old Action for the same Text remained reusable",
    )
    settings.remap_prompt_text = fourth_text
    check(settings.remap_action == new_fourth, "Selecting the Text did not resolve its replacement Action")

    third_text = bpy.data.texts.new("第三段")
    third_text.write("A person draws both hands inward.")
    third_action = bpy.data.actions.new("BAW_Third_Recovery")
    third_action["bam_role"] = "RETARGET_OUTPUT"
    third_action["bam_target_object"] = armature.name
    third_action["bam_motion_frame_start"] = 224
    third_action["bam_motion_frame_end"] = 293
    third_action["baw_source_action"] = wrong_source.name
    third_action.use_frame_range = True
    third_action.frame_start = 224
    third_action.frame_end = 293
    auto_director._persist_text_action_link(
        third_text,
        third_action,
        wrong_source,
        replace=False,
    )
    new_fourth["bam_motion_frame_start"] = 293
    new_fourth["bam_motion_frame_end"] = 342
    new_fourth.use_frame_range = True
    new_fourth.frame_start = 293
    new_fourth.frame_end = 342
    recovery_track = animation_data.nla_tracks.new()
    recovery_track.name = "BAW_上一段_第三段回归"
    recovery_strip = recovery_track.strips.new("第三段", 224, new_fourth)
    recovery_strip.action_frame_start = 224
    recovery_strip.action_frame_end = 293
    recovery_strip.frame_start = 224
    recovery_strip.frame_end = 293
    check(
        auto_director._repair_owned_nla_clip_references(scene) == 1,
        "Mismatched BA-owned NLA strip was not repaired",
    )
    check(recovery_strip.action == third_action, "Third-Clip NLA strip did not recover its correct Action")
    animation_data.nla_tracks.remove(recovery_track)

    pose_bone.constraints.remove(visible_constraint)
    auxiliary_pose_bone.constraints.remove(auxiliary_constraint)
    animation_data.action = None
    for track in tuple(animation_data.nla_tracks):
        animation_data.nla_tracks.remove(track)
    settings.remap_action = None
    bpy.data.actions.remove(previous_action)
    bpy.data.actions.remove(output_action)
    source_holder.animation_data.action = None
    bpy.data.actions.remove(source_action)
    for action in (new_fourth, wrong_output, fourth_source, wrong_source, third_action):
        if bpy.data.actions.get(action.name) is not None:
            bpy.data.actions.remove(action)
    bpy.data.objects.remove(source_holder, do_unlink=True)
    bpy.data.texts.remove(clip_prompt)
    bpy.data.texts.remove(fourth_text)
    bpy.data.texts.remove(third_text)
    pose_bone.location.x = 0.0

    scene.frame_start = 1
    scene.frame_set(100)
    settings.preroll_margin = 60
    preroll_plan = dict(structured)
    auto_director._prepare_start_behavior(bpy.context, settings, preroll_plan)
    bridge = scene.ba_motion_bridge_settings
    check(settings.start_behavior == "PREROLL" and settings.preroll_start_frame == 40, "No-motion preroll was not selected")
    check(bridge.use_start_buffer, "Motion Bridge start buffer was not enabled")
    check((bridge.settle_frames, bridge.transition_frames) == (0, 60), "Auto Director did not configure transition-only preroll")
    check("buffer_frames" not in preroll_plan["start_behavior"], "Plan still records a separate stable buffer")
    check(preroll_plan["start_behavior"]["transition_frames"] == 60, "Plan did not record the transition margin")

    scene.render.fps = 24
    scene.render.fps_base = 1.0
    scene.frame_start = 1
    scene.frame_end = 250
    scene.use_preview_range = False
    scene.frame_set(100)
    settings.timeline_before_json = json.dumps(auto_director._timeline_snapshot(scene))
    settings.start_behavior = "PREROLL"
    settings.motion_start_frame = 100
    settings.preroll_start_frame = 40
    auto_director._finish_timeline(scene, settings, structured, completed=True)
    check(scene.render.fps == 24 and scene.frame_end == 250, "Completed Clip timeline changed the scene FPS or shortened the timeline")
    check(scene.use_preview_range and scene.frame_preview_start == 40 and scene.frame_current == 40, "Preroll preview range was not applied")
    auto_director._finish_timeline(scene, settings, structured, completed=False)
    check(scene.render.fps == 24 and scene.frame_end == 250 and scene.frame_current == 100, "Cancelled Clip timeline was not restored")
    check(not scene.use_preview_range, "Cancelled Clip preview range was not restored")

    settings.creative_prompt = "教室里角色向前走两步；然后温暖地挥手"
    settings.total_frames = 120

    panels = importlib.import_module(addon.__name__ + ".panels")
    events = []
    panel = SimpleNamespace(layout=LayoutProbe(events))
    scene.baw_settings.workspace_mode = "AUTO"
    panels.BAW_PT_main.draw(panel, bpy.context)
    operators = [event[1] for event in events if event[0] == "operator"]
    check("baw.auto_run" in operators, "Auto Director panel has no run button")
    check(any(event[0] == "template_ID" and event[1] == "prompt_text" for event in events), "Auto Director panel has no multiline Text selector")
    check("baw.auto_prompt_edit" in operators, "Auto Director panel has no multiline editor button")
    check(any(event[0] == "prop" and event[1] == "total_frames" for event in events), "Auto Director panel has no total-frames field")
    check("baw.auto_import_existing" in operators, "Standalone Action reuse panel has no single-Action import button")
    check("baw.auto_remap_existing" not in operators, "Action reuse panel shows an irrelevant same-model operation")
    check("baw.auto_import_all_existing" not in operators, "Action reuse panel shows batch import before a source and blank target are ready")
    check(any(event[0] == "prop" and event[1] == "remap_prompt_text" for event in events), "Action reuse panel has no Text-first selector")
    check(any(event[0] == "prop" and event[1] == "remap_action" for event in events), "Standalone Action reuse panel has no source-Action selector")
    check(any(event[0] == "prop" and event[1] == "reuse_target_rig" for event in events), "Standalone Action reuse panel has no new-model selector")
    check("baw.auto_compile_plan" not in operators, "Auxiliary plan button is visible in the default compact layout")
    check(operators.count("baw.auto_run") == 1, "Default Auto Director layout does not have exactly one primary action")

    ui_action = bpy.data.actions.new("BAW_UI_Reuse_Action")
    ui_action["bam_role"] = "RETARGET_OUTPUT"
    ui_action["bam_target_object"] = armature.name
    settings.remap_action = ui_action
    settings.reuse_target_rig = armature
    same_model_events = []
    panel.layout = LayoutProbe(same_model_events)
    panels.BAW_PT_main.draw(panel, bpy.context)
    same_model_operators = [event[1] for event in same_model_events if event[0] == "operator"]
    check(same_model_operators.count("baw.auto_remap_existing") == 1, "Same-model reuse has no single replace operation")
    check("baw.auto_import_existing" not in same_model_operators, "Same-model reuse still shows the new-model import operation")
    check("baw.auto_import_all_existing" not in same_model_operators, "Same-model reuse still shows batch import")

    blank_target_data = bpy.data.armatures.new("BAW_UI_Blank_Target_Data")
    blank_target = bpy.data.objects.new("BAW_UI_Blank_Target", blank_target_data)
    scene.collection.objects.link(blank_target)
    settings.reuse_target_rig = blank_target
    new_model_events = []
    panel.layout = LayoutProbe(new_model_events)
    panels.BAW_PT_main.draw(panel, bpy.context)
    new_model_operators = [event[1] for event in new_model_events if event[0] == "operator"]
    check(new_model_operators.count("baw.auto_import_existing") == 1, "New-model reuse has no single import operation")
    check(new_model_operators.count("baw.auto_import_all_existing") == 1, "Blank new-model reuse has no batch import operation")
    check("baw.auto_remap_existing" not in new_model_operators, "New-model reuse still shows the same-model replace operation")

    settings.remap_action = None
    settings.reuse_target_rig = None
    bpy.data.actions.remove(ui_action)
    bpy.data.objects.remove(blank_target, do_unlink=True)
    bpy.data.armatures.remove(blank_target_data)
    settings.show_advanced = True
    advanced_events = []
    panel.layout = LayoutProbe(advanced_events)
    panels.BAW_PT_main.draw(panel, bpy.context)
    advanced_operators = [event[1] for event in advanced_events if event[0] == "operator"]
    check("baw.auto_compile_plan" in advanced_operators, "Advanced layout has no plan-only button")
    check("baw.auto_build_scene" in advanced_operators, "Advanced layout has no scene-only button")
    check("baw.auto_remap_existing" not in advanced_operators, "Compact Action reuse panel exposed an irrelevant operation in advanced settings")
    check(sum(1 for event in advanced_events if event[0] == "prop" and event[1] == "total_frames") == 1, "Total frames is missing or duplicated")
    check(not any(event[0] == "prop" and event[1] in {"parse_prompt_parameters", "generate_pose_anchors", "duration_seconds", "fps"} for event in advanced_events), "Removed multi-segment timing controls remain visible")
    check(any(event[0] == "prop" and event[1] == "preroll_margin" for event in advanced_events), "Advanced layout has no preroll margin")
    check(not any(event[0] == "prop" and event[1] == "preroll_transition_frames" for event in advanced_events), "Advanced layout still has a redundant preroll transition")
    check(any(event[0] == "prop" and event[1] == "motion_space" for event in advanced_events), "Advanced layout has no PMB 0.9.1 motion-space setting")
    check(any(event[0] == "prop" and event[1] == "use_end_effector_guard" for event in advanced_events), "Advanced layout has no PMB 0.9.1 end-effector guard")
    check(any(event[0] == "prop" and event[1] == "end_effector_guard_strength" for event in advanced_events), "Advanced layout has no PMB 0.9.1 guard strength")
    settings.show_advanced = False
    settings.status_message = "这是一个很长的自动导演状态说明，用来验证窄面板会按可用宽度自动换行，而不是要求用户把右侧面板横向拉宽。"
    wrapped_events = []
    panel.layout = LayoutProbe(wrapped_events)
    panels.BAW_PT_main.draw(panel, bpy.context)
    wrapped_status_labels = [event[1] for event in wrapped_events if event[0] == "label" and ("自动导演状态" in event[1] or "右侧面板" in event[1])]
    check(len(wrapped_status_labels) >= 2, "Long Auto Director status was not wrapped")
    settings.status_message = "方案已准备"
    settings.state = "RUNNING"
    settings.progress = 0.42
    running_events = []
    panel.layout = LayoutProbe(running_events)
    panels.BAW_PT_main.draw(panel, bpy.context)
    check(any(event[0] == "progress" and abs(event[1] - 0.42) < 1e-6 for event in running_events), "Running progress was not drawn")
    check(any(event[0] == "operator" and event[1] == "baw.auto_cancel" for event in running_events), "Running panel has no cancel button")
    settings.state = "PLAN_READY"
    scene.baw_settings.workspace_mode = "MANUAL"
    expected_stage_actions = {
        "PROJECT": {"baw.initialize_workflow"},
        "CLEANUP": {"baw.clean_mocap_action", "baw.create_correction_layer"},
        "SHOT": {"baw.create_camera_rig", "baw.create_light_rig"},
        "DELIVERY": {"baw.prepare_preview", "baw.audit"},
    }
    for stage in ("PROJECT", "MOTION", "CLEANUP", "SHOT", "DELIVERY", "LEGACY"):
        scene.baw_settings.manual_stage = stage
        stage_events = []
        panel.layout = LayoutProbe(stage_events)
        panels.BAW_PT_main.draw(panel, bpy.context)
        stage_actions = {event[1] for event in stage_events if event[0] == "operator"}
        check(expected_stage_actions.get(stage, set()).issubset(stage_actions), f"Manual stage {stage} is missing its primary action")
        if stage == "PROJECT":
            check("baw.setup_project" not in stage_actions and "baw.setup_scene" not in stage_actions, "Redundant project setup buttons remain visible")
        if stage == "DELIVERY":
            check("baw.cleanup_cache" not in stage_actions, "Destructive maintenance is visible before expanding Safe Cleanup")
    panel_types = sorted(name for name in dir(bpy.types) if name.startswith("BAW_PT_"))
    check(panel_types == ["BAW_PT_main"], f"Redundant BA Workflow panels remain registered: {panel_types}")
    scene.baw_settings.workspace_mode = "AUTO"

    settings.build_set = True
    settings.build_lighting = True
    settings.build_camera = True
    check(bpy.ops.baw.auto_build_scene() == {"FINISHED"}, "Scene build failed")
    first_count = settings.generated_object_count
    check(first_count == 10, f"Unexpected generated object count: {first_count}")
    check(scene.world != foreign_world, "Auto lighting did not use an isolated World")
    check(abs(foreign_background.inputs["Strength"].default_value - 0.73) < 1e-6, "User World changed")
    check(scene.camera != foreign_camera, "Auto camera was not activated")
    check(abs(camera_data.lens - 31.0) < 1e-6, "User camera changed")
    auto_objects = [obj for obj in scene.objects if str(obj.get("baw_role", "")).startswith("AUTO_DIRECTOR::")]
    check(len(auto_objects) == first_count, "Generated object ownership markers are incomplete")
    check(body.name in scene.objects and armature.name in scene.objects, "User model changed during build")
    first_data_count = sum(
        1
        for datablocks in (bpy.data.meshes, bpy.data.lights, bpy.data.cameras)
        for datablock in datablocks
        if str(datablock.get("baw_role", "")).startswith("AUTO_DIRECTOR::")
    )

    check(bpy.ops.baw.auto_build_scene() == {"FINISHED"}, "Idempotent scene rebuild failed")
    rebuilt = [obj for obj in scene.objects if str(obj.get("baw_role", "")).startswith("AUTO_DIRECTOR::")]
    check(len(rebuilt) == first_count, "Scene rebuild duplicated generated objects")
    rebuilt_data_count = sum(
        1
        for datablocks in (bpy.data.meshes, bpy.data.lights, bpy.data.cameras)
        for datablock in datablocks
        if str(datablock.get("baw_role", "")).startswith("AUTO_DIRECTOR::")
    )
    check(rebuilt_data_count == first_data_count, "Scene rebuild leaked generated data blocks")

    check(bpy.ops.baw.auto_clear_scene() == {"FINISHED"}, "Generated scene cleanup failed")
    check(not [obj for obj in scene.objects if str(obj.get("baw_role", "")).startswith("AUTO_DIRECTOR::")], "Generated objects survived cleanup")
    check(
        not [
            datablock
            for datablocks in (bpy.data.meshes, bpy.data.lights, bpy.data.cameras)
            for datablock in datablocks
            if str(datablock.get("baw_role", "")).startswith("AUTO_DIRECTOR::")
        ],
        "Generated data blocks survived cleanup",
    )
    check(scene.world == foreign_world, "User World was not restored")
    check(scene.camera == foreign_camera, "User camera was not restored")
    check(body.name in scene.objects and armature.name in scene.objects, "Cleanup deleted user model data")
    check(foreign_plan.as_string() == "user-owned", "Cleanup changed foreign text")

    print(
        "BAW_AUTO_DIRECTOR_SMOKE="
        + json.dumps(
            {
                "status": "PASS",
                "environment": plan["environment"],
                "lighting": plan["lighting"],
                "prompt_blocks": len(plan["prompt_blocks"]),
                "generated_objects": first_count,
                "user_context_restored": True,
                "cloud_generation_invoked": False,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
