from __future__ import annotations

import shutil

import bpy
from mathutils import Vector

from .utils import (
    build_audit,
    cache_is_safe,
    create_project_folders,
    ensure_object,
    ensure_scene_id,
    ensure_scene_collections,
    find_armature,
    find_character_object,
    find_owned_object,
    generated_cache_dir,
    is_owned,
    iter_action_fcurves,
    mark_owned,
    object_bounds_world,
    operator_available,
    recreate_generated_cache,
    resolve_project_root,
    simplify_fcurve,
    smooth_fcurve,
    unwrap_euler_fcurve,
    write_audit_text,
)


class BAW_OT_setup_project(bpy.types.Operator):
    bl_idname = "baw.setup_project"
    bl_label = "创建项目目录"
    bl_description = "创建固定项目目录；不会覆盖已有文件"
    bl_options = {"REGISTER"}

    def execute(self, context):
        try:
            root = resolve_project_root(context.scene.baw_settings)
            if root is None:
                self.report({"ERROR"}, "请先选择项目根目录")
                return {"CANCELLED"}
            create_project_folders(root)
        except (OSError, ValueError) as exc:
            self.report({"ERROR"}, f"创建目录失败：{exc}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"项目目录已就绪：{root}")
        return {"FINISHED"}


class BAW_OT_setup_scene(bpy.types.Operator):
    bl_idname = "baw.setup_scene"
    bl_label = "初始化场景结构"
    bl_description = "创建统一的角色、动捕、灯光、相机和输出集合"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        ensure_scene_collections()
        self.report({"INFO"}, "场景集合结构已初始化；时间轴设置保持不变")
        return {"FINISHED"}


class BAW_OT_initialize_workflow(bpy.types.Operator):
    bl_idname = "baw.initialize_workflow"
    bl_label = "一键初始化动画工程"
    bl_description = "初始化安全场景集合；已选择项目目录时同时创建固定工程结构，不覆盖已有文件"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.baw_settings
        ensure_scene_collections()
        project_ready = False
        try:
            root = resolve_project_root(settings)
            if root is not None:
                create_project_folders(root)
                project_ready = True
        except (OSError, ValueError) as exc:
            settings.last_workflow_summary = f"场景已初始化；项目目录未创建：{exc}"
            self.report({"WARNING"}, settings.last_workflow_summary)
            return {"FINISHED"}
        settings.last_workflow_summary = (
            "场景集合与项目目录已就绪" if project_ready else "场景集合已就绪；可稍后选择项目目录"
        )
        self.report({"INFO"}, settings.last_workflow_summary)
        return {"FINISHED"}


class BAW_OT_create_light_rig(bpy.types.Operator):
    bl_idname = "baw.create_light_rig"
    bl_label = "自动三点布光"
    bl_description = "根据活动角色尺寸创建可直接调整的主光、补光和轮廓光"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        collections = ensure_scene_collections()
        collection = collections["BAW_50_LIGHTS"]
        scene_id = ensure_scene_id(context.scene)
        character = find_character_object(context)
        center, height = object_bounds_world(character)
        target = center + Vector((0.0, 0.0, height * 0.12))
        power = context.scene.baw_settings.light_power

        target_obj = ensure_object("BAW_Light_Target", None, collection, expected_type="EMPTY")
        target_obj.empty_display_type = "SPHERE"
        target_obj.empty_display_size = max(height * 0.05, 0.05)
        target_obj.location = target

        specs = (
            ("BAW_Key", (0.85, -1.15, 0.75), power, (1.0, 0.72, 0.52), 0.65),
            ("BAW_Fill", (-0.9, -0.75, 0.35), power * 0.35, (0.48, 0.68, 1.0), 0.9),
            ("BAW_Rim", (0.25, 0.95, 0.85), power * 0.75, (0.62, 0.76, 1.0), 0.5),
        )
        for name, offset, energy, color, size_factor in specs:
            light_obj = find_owned_object(name, collection, expected_type="LIGHT")
            if light_obj is None:
                light_data = bpy.data.lights.new(name=name, type="AREA")
                mark_owned(light_data, name, scene_id)
                light_obj = ensure_object(name, light_data, collection, expected_type="LIGHT")
            elif light_obj.data.type != "AREA" or not is_owned(light_obj.data, name, scene_id):
                light_data = bpy.data.lights.new(name=name, type="AREA")
                mark_owned(light_data, name, scene_id)
                light_obj.data = light_data
            else:
                light_data = light_obj.data
            light_data.energy = energy
            light_data.color = color
            light_data.shape = "DISK"
            light_data.size = max(height * size_factor, 0.2)
            light_obj.location = center + Vector(offset) * height
            for constraint in tuple(light_obj.constraints):
                if constraint.name == f"BAW_Aim_{name}" and constraint.type == "DAMPED_TRACK":
                    light_obj.constraints.remove(constraint)
            constraint = light_obj.constraints.new("DAMPED_TRACK")
            constraint.name = f"BAW_Aim_{name}"
            constraint.target = target_obj
            constraint.track_axis = "TRACK_NEGATIVE_Z"

        current_world = context.scene.world
        preserved_user_world = current_world is not None and not is_owned(current_world)
        if not preserved_user_world:
            world = next(
                (
                    item
                    for item in bpy.data.worlds
                    if is_owned(item, role="BAW_World", scene_id=scene_id) and item.library is None
                ),
                None,
            )
            if world is None:
                world = bpy.data.worlds.new("BAW_World")
                mark_owned(world, "BAW_World", scene_id)
            context.scene.world = world
            world.use_nodes = True
            background = world.node_tree.nodes.get("Background") if world.node_tree else None
            if background:
                background.inputs["Color"].default_value = (0.025, 0.035, 0.055, 1.0)
                background.inputs["Strength"].default_value = 0.22

        suffix = "；已保留现有 World" if preserved_user_world else ""
        self.report({"INFO"}, f"三点光已按角色尺寸创建{suffix}")
        return {"FINISHED"}


class BAW_OT_create_camera_rig(bpy.types.Operator):
    bl_idname = "baw.create_camera_rig"
    bl_label = "创建镜头构图"
    bl_description = "按所选景别创建带目标点的可控相机"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        collections = ensure_scene_collections()
        collection = collections["BAW_60_CAMERAS"]
        scene_id = ensure_scene_id(context.scene)
        character = find_character_object(context)
        center, height = object_bounds_world(character)
        shot = context.scene.baw_settings.shot_type

        root = ensure_object("BAW_Camera_Root", None, collection, expected_type="EMPTY")
        root.empty_display_type = "PLAIN_AXES"
        root.empty_display_size = max(height * 0.2, 0.2)
        root.location = center
        root.rotation_euler = (0.0, 0.0, 0.0)

        target = ensure_object("BAW_Camera_Target", None, collection, expected_type="EMPTY")
        target.empty_display_type = "SPHERE"
        target.empty_display_size = max(height * 0.04, 0.04)
        target.parent = root

        offsets = {
            "FULL": (Vector((0.0, -2.8, 0.08)), Vector((0.0, 0.0, 0.03)), 50.0),
            "MEDIUM": (Vector((0.0, -1.75, 0.18)), Vector((0.0, 0.0, 0.18)), 55.0),
            "CLOSE": (Vector((0.0, -0.92, 0.34)), Vector((0.0, 0.0, 0.34)), 70.0),
            "ACTION": (Vector((1.05, -2.0, 0.28)), Vector((0.0, 0.0, 0.20)), 42.0),
        }
        camera_offset, target_offset, lens = offsets[shot]
        target.location = target_offset * height

        camera = find_owned_object("BAW_Camera", collection, expected_type="CAMERA")
        if camera is None:
            camera_data = bpy.data.cameras.new("BAW_Camera")
            mark_owned(camera_data, "BAW_Camera", scene_id)
            camera = ensure_object("BAW_Camera", camera_data, collection, expected_type="CAMERA")
        elif not is_owned(camera.data, "BAW_Camera", scene_id):
            camera_data = bpy.data.cameras.new("BAW_Camera")
            mark_owned(camera_data, "BAW_Camera", scene_id)
            camera.data = camera_data
        else:
            camera_data = camera.data
        camera_data.lens = lens
        camera_data.dof.use_dof = True
        camera_data.dof.focus_object = target
        camera_data.dof.aperture_fstop = 4.0

        camera.parent = root
        camera.location = camera_offset * height
        camera.rotation_euler = (0.0, 0.0, 0.0)
        for constraint in tuple(camera.constraints):
            if constraint.name == "BAW_Aim" and constraint.type == "DAMPED_TRACK":
                camera.constraints.remove(constraint)
        constraint = camera.constraints.new("DAMPED_TRACK")
        constraint.name = "BAW_Aim"
        constraint.target = target
        constraint.track_axis = "TRACK_NEGATIVE_Z"
        context.scene.camera = camera
        root["baw_shot_type"] = shot

        labels = {"FULL": "全身", "MEDIUM": "中景", "CLOSE": "近景", "ACTION": "动作"}
        self.report({"INFO"}, f"{labels[shot]}镜头已创建")
        return {"FINISHED"}


class BAW_OT_add_camera_cut(bpy.types.Operator):
    bl_idname = "baw.add_camera_cut"
    bl_label = "当前帧设为切镜"
    bl_description = "在当前帧创建镜头标记并绑定活动相机"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        if scene.camera is None:
            self.report({"ERROR"}, "场景没有活动相机")
            return {"CANCELLED"}
        frame = scene.frame_current
        name = f"BAW_SHOT_{frame:04d}_{scene.camera.name}"
        marker = scene.timeline_markers.new(name, frame=frame)
        marker.camera = scene.camera
        self.report({"INFO"}, f"已在第 {frame} 帧绑定 {scene.camera.name}")
        return {"FINISHED"}


class BAW_OT_clean_mocap_action(bpy.types.Operator):
    bl_idname = "baw.clean_mocap_action"
    bl_label = "复制并清理动捕"
    bl_description = "先复制原动作，再平滑和简化曲线；原动作不会被修改"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        armature = find_armature(context)
        if armature is None or armature.animation_data is None or armature.animation_data.action is None:
            self.report({"ERROR"}, "请选择带动作的角色骨架")
            return {"CANCELLED"}

        settings = context.scene.baw_settings
        original = armature.animation_data.action
        if len(getattr(original, "slots", ())) > 1:
            self.report({"ERROR"}, "多目标 Action 暂不自动清理；请先拆分为单目标 Action")
            return {"CANCELLED"}
        original_count = sum(len(curve.keyframe_points) for curve in iter_action_fcurves(original))
        original.use_fake_user = True
        cleaned = original.copy()
        cleaned.name = f"{original.name}_BAW_Clean"
        cleaned["baw_source_action"] = original.name
        cleaned.use_fake_user = True

        removed = 0
        protected = 0
        for curve in iter_action_fcurves(cleaned):
            if curve.data_path.endswith(("rotation_quaternion", "rotation_axis_angle")):
                protected += 1
                continue
            if curve.data_path.endswith("rotation_euler"):
                unwrap_euler_fcurve(curve)
            smooth_fcurve(curve, settings.smooth_strength, settings.smooth_passes)
            removed += simplify_fcurve(curve, settings.simplify_tolerance)

        armature.animation_data.action = cleaned
        final_count = sum(len(curve.keyframe_points) for curve in iter_action_fcurves(cleaned))
        suffix = f"；为防旋转翻转，保留 {protected} 条四元数/轴角曲线" if protected else ""
        settings.last_clean_summary = f"{original.name} → {cleaned.name}：{original_count} → {final_count} 点"
        self.report({"INFO"}, f"已生成 {cleaned.name}：{original_count} → {final_count} 个关键帧点{suffix}")
        return {"FINISHED"}


class BAW_OT_create_correction_layer(bpy.types.Operator):
    bl_idname = "baw.create_correction_layer"
    bl_label = "创建人工修正层"
    bl_description = "把当前动作放入只读式 NLA 底层，并创建只记录修正骨骼的新动作"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        armature = find_armature(context)
        if armature is None or armature.animation_data is None or armature.animation_data.action is None:
            self.report({"ERROR"}, "请选择带清理动作的角色骨架")
            return {"CANCELLED"}

        animation_data = armature.animation_data
        base_action = animation_data.action
        if len(getattr(base_action, "slots", ())) > 1:
            self.report({"ERROR"}, "多目标 Action 暂不自动转换为修正层")
            return {"CANCELLED"}
        base_action.use_fake_user = True
        base_blend_type = animation_data.action_blend_type
        base_extrapolation = animation_data.action_extrapolation
        base_influence = animation_data.action_influence
        frame_start = int(base_action.frame_range[0])
        track_name = f"BAW_MOCAP_BASE::{base_action.name}"
        if animation_data.nla_tracks.get(track_name) is not None:
            self.report({"ERROR"}, f"{base_action.name} 已经存在人工修正底层")
            return {"CANCELLED"}
        for old_track in animation_data.nla_tracks:
            if old_track.name.startswith("BAW_MOCAP_BASE"):
                old_track.mute = True
        track = animation_data.nla_tracks.new()
        track.name = track_name
        strip = track.strips.new(base_action.name, frame_start, base_action)
        strip.name = f"BASE_{base_action.name}"
        strip.blend_type = base_blend_type
        strip.extrapolation = base_extrapolation
        strip.influence = base_influence
        track.lock = True
        track.mute = False

        animation_data.action = None
        correction = bpy.data.actions.new(f"{base_action.name}_CORR")
        correction.use_fake_user = True
        correction["baw_role"] = "CORRECTION"
        correction["baw_source_action"] = base_action.name
        animation_data.action = correction
        animation_data.action_blend_type = "REPLACE"
        animation_data.action_extrapolation = "NOTHING"
        animation_data.use_nla = True

        self.report({"INFO"}, f"已创建修正层 {correction.name}；只给需要修复的骨骼打关键帧")
        return {"FINISHED"}


class BAW_OT_create_pro_camera_rig(bpy.types.Operator):
    bl_idname = "baw.create_pro_camera_rig"
    bl_label = "创建专业相机 Rig"
    bl_description = "调用官方 Add Camera Rigs 扩展创建 Dolly、Crane 或 2D Rig"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        if not operator_available(bpy.ops.object.build_camera_rig):
            self.report({"ERROR"}, "未检测到 Add Camera Rigs 扩展")
            return {"CANCELLED"}
        if context.object and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        character = find_character_object(context)
        center, _height = object_bounds_world(character)
        original_cursor = context.scene.cursor.location.copy()
        context.scene.cursor.location = center
        try:
            result = bpy.ops.object.build_camera_rig(mode=context.scene.baw_settings.camera_rig_mode)
        except (AttributeError, RuntimeError) as exc:
            self.report({"ERROR"}, f"相机 Rig 创建失败：{exc}")
            return {"CANCELLED"}
        finally:
            context.scene.cursor.location = original_cursor
        if result != {"FINISHED"}:
            self.report({"ERROR"}, "Add Camera Rigs 未完成创建")
            return {"CANCELLED"}
        self.report({"INFO"}, f"已创建 {context.scene.baw_settings.camera_rig_mode} 相机 Rig")
        return {"FINISHED"}


class BAW_OT_prepare_preview(bpy.types.Operator):
    bl_idname = "baw.prepare_preview"
    bl_label = "设置快速预览输出"
    bl_description = "设置 720p/Eevee/H.264 预览参数，保留工程帧率和动画范围"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        scene.render.engine = "BLENDER_EEVEE"
        scene.render.resolution_x = 1280
        scene.render.resolution_y = 720
        scene.render.resolution_percentage = 100
        scene.render.image_settings.media_type = "VIDEO"
        scene.render.image_settings.file_format = "FFMPEG"
        scene.render.ffmpeg.format = "MPEG4"
        scene.render.ffmpeg.codec = "H264"
        scene.render.ffmpeg.constant_rate_factor = "MEDIUM"

        try:
            root = resolve_project_root(scene.baw_settings)
        except ValueError as exc:
            root = None
            self.report({"WARNING"}, f"项目路径未用于输出：{exc}")
        if root is not None:
            output = root / "60_renders_preview" / "preview_"
            scene.render.filepath = str(output)
        elif bpy.data.filepath:
            scene.render.filepath = "//60_renders_preview/preview_"
        self.report({"INFO"}, "快速预览参数已设置")
        return {"FINISHED"}


class BAW_OT_audit(bpy.types.Operator):
    bl_idname = "baw.audit"
    bl_label = "运行交付检查"
    bl_description = "检查骨架、动作、相机、灯光、贴图和输出设置"
    bl_options = {"REGISTER"}

    def execute(self, context):
        report = build_audit(context)
        write_audit_text(report)
        warning_count = len(report["warnings"])
        context.scene.baw_settings.last_audit_summary = (
            f"发现 {warning_count} 项待处理" if warning_count else "检查通过，未发现常见问题"
        )
        if warning_count:
            self.report({"WARNING"}, f"检查完成：发现 {warning_count} 项待处理，详见 BAW_检查报告")
        else:
            self.report({"INFO"}, "检查通过，未发现常见问题")
        return {"FINISHED"}


class BAW_OT_cleanup_cache(bpy.types.Operator):
    bl_idname = "baw.cleanup_cache"
    bl_label = "清理本工具缓存"
    bl_description = "仅删除带工作区标记的 50_cache/baw_generated 目录内容"
    bl_options = {"REGISTER"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        try:
            root = resolve_project_root(context.scene.baw_settings)
            if root is None:
                self.report({"ERROR"}, "请先选择项目根目录")
                return {"CANCELLED"}
            cache = generated_cache_dir(root)
            if not cache_is_safe(root, cache):
                self.report({"ERROR"}, "安全检查失败：项目与缓存所有权标记不匹配，或路径包含目录联接")
                return {"CANCELLED"}
            if cache.exists():
                shutil.rmtree(cache)
            recreate_generated_cache(root)
        except (OSError, ValueError) as exc:
            self.report({"ERROR"}, f"缓存清理失败：{exc}")
            return {"CANCELLED"}
        self.report({"INFO"}, "本工具生成的缓存已清理")
        return {"FINISHED"}


class BAW_OT_cleanup_bridge_temporary(bpy.types.Operator):
    bl_idname = "baw.cleanup_bridge_temporary"
    bl_label = "清理 Bridge 安全临时资源"
    bl_description = "仅调用 Motion Bridge 的所有权标记清理；不会删除输出 Action、模型、贴图或用户数据"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, _context):
        try:
            return operator_available(bpy.ops.ba_motion_bridge.cleanup_temporary)
        except AttributeError:
            return False

    def execute(self, _context):
        try:
            result = bpy.ops.ba_motion_bridge.cleanup_temporary("EXEC_DEFAULT")
        except (AttributeError, RuntimeError) as exc:
            self.report({"ERROR"}, f"Bridge 临时资源清理失败：{exc}")
            return {"CANCELLED"}
        if result != {"FINISHED"}:
            self.report({"ERROR"}, f"Bridge 临时资源清理未完成：{result}")
            return {"CANCELLED"}
        self.report({"INFO"}, "Bridge 临时资源已按所有权标记清理")
        return {"FINISHED"}


CLASSES = (
    BAW_OT_initialize_workflow,
    BAW_OT_setup_project,
    BAW_OT_setup_scene,
    BAW_OT_create_light_rig,
    BAW_OT_create_camera_rig,
    BAW_OT_add_camera_cut,
    BAW_OT_clean_mocap_action,
    BAW_OT_create_correction_layer,
    BAW_OT_create_pro_camera_rig,
    BAW_OT_prepare_preview,
    BAW_OT_audit,
    BAW_OT_cleanup_cache,
    BAW_OT_cleanup_bridge_temporary,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
