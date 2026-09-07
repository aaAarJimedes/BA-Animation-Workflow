import unicodedata

import bpy

from .utils import external_addon_status, operator_available


def _operator(path: str):
    namespace, name = path.split(".", 1)
    try:
        return getattr(getattr(bpy.ops, namespace), name)
    except AttributeError:
        return None


def _has_operator(path: str) -> bool:
    operator = _operator(path)
    return operator is not None and operator_available(operator)


def _component_ready(name: str, status: dict[str, bool]) -> bool:
    if not status.get(name, False):
        return False
    requirements = {
        "BlendCap": ("blendcap.apply_retarget",),
        "BlendCap Motion Bridge": ("blendcap_motion_bridge.detect", "blendcap_motion_bridge.apply_retarget_fk_safe"),
        "Proscenium": ("proscenium.connect", "proscenium.generate", "proscenium.accept"),
        "Proscenium Motion Bridge": ("ba_motion_bridge.accept_and_retarget", "ba_motion_bridge.restore_previous_state"),
        "Add Camera Rigs": ("object.build_camera_rig",),
    }
    return all(_has_operator(path) for path in requirements.get(name, ()))


def _bridge_settings(context):
    return getattr(context.scene, "ba_motion_bridge_settings", None)


def _wrap_width(context) -> int:
    region = getattr(context, "region", None)
    width = getattr(region, "width", 300) if region is not None else 300
    return max(18, min(52, int((width - 36) / 7)))


def _wrapped(layout, context, text: str, icon: str = "NONE") -> None:
    if not text:
        return
    # CJK glyphs occupy about two Latin cells; counting codepoints clipped
    # Chinese help text even though the same width fit English correctly.
    width = _wrap_width(context)
    lines = []
    for paragraph in str(text).splitlines():
        line = ""
        used = 0
        for char in paragraph:
            cells = 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1
            if line and used + cells > width:
                lines.append(line.rstrip())
                line, used = "", 0
            if not line and char.isspace():
                continue
            line += char
            used += cells
        lines.append(line)
    for index, line in enumerate(lines or [str(text)]):
        layout.label(text=line, icon=icon if index == 0 else "BLANK1")


def _primary(layout, operator: str, text: str, icon: str):
    column = layout.column()
    column.scale_y = 1.4
    return column.operator(operator, text=text, icon=icon)


def _draw_action_reuse(layout, context, settings) -> None:
    remap = layout.box()
    remap.label(text="动作复用", icon="ACTION")
    remap.label(text="1. 选择动作文本块", icon="TEXT")
    remap.prop(settings, "remap_prompt_text", text="文本块")
    remap.prop(settings, "remap_action", text="关联动作")
    selected_action = settings.remap_action
    if selected_action is not None:
        start = int(round(float(selected_action.get("bam_motion_frame_start", selected_action.frame_range[0]))))
        end = int(round(float(selected_action.get("bam_motion_frame_end", selected_action.frame_range[1]))))
        source_target = str(selected_action.get("bam_target_object", "") or "未知模型")
        source_name = str(selected_action.get("baw_source_action", "") or "")
        orphan_source = selected_action.name.startswith("Proscenium_Motion:")
        if orphan_source:
            _wrapped(remap, context, f"{start}–{end} 帧 · 生成成功，等待输出到角色", "RECOVER_LAST")
            remap.label(text="可直接导入，无需重新生成", icon="CHECKMARK")
        else:
            _wrapped(remap, context, f"{start}–{end} 帧 · 来源 {source_target}", "TIME")
        if source_name or orphan_source:
            remap.label(text="干净源动作已关联", icon="CHECKMARK")
        else:
            _wrapped(remap, context, "尚未找到干净源动作；执行时会尝试自动识别。", "ERROR")
    elif settings.remap_prompt_text is not None:
        _wrapped(remap, context, "该文本块尚未找到可复用动作。", "ERROR")
    remap.label(text="2. 选择接收模型", icon="ARMATURE_DATA")
    remap.prop(settings, "reuse_target_rig", text="目标模型")
    remap.prop(settings, "reuse_foot_contact")
    if settings.reuse_foot_contact:
        _wrapped(remap, context, "仅本次复用 · MMD 实验功能；支撑脚锁定，抬脚释放。关闭后再次映射可对比。", "EXPERIMENTAL")
    if selected_action is not None and selected_action.get("baw_foot_contact_enabled"):
        remap.label(text="当前动作：已应用实验防脚滑", icon="CHECKMARK")
    remap.prop(settings, "reuse_seam_smoothing")
    if settings.reuse_seam_smoothing:
        remap.prop(settings, "reuse_seam_mode", text="过渡方式")
        remap.prop(settings, "reuse_seam_frames", text="总过渡帧数")
        if settings.reuse_seam_mode == 'SPLIT':
            _wrapped(remap, context, "会修改前段末尾与本段开头，成对备份；总帧数均分，奇数多一帧给本段。", "EXPERIMENTAL")
        else:
            _wrapped(remap, context, "重新映射后生效；只平滑本段开头，不修改上一段。无相邻前段时跳过。", "EXPERIMENTAL")
        if settings.reuse_foot_contact:
            _wrapped(remap, context, "同时开启时，过渡窗口优先防突变，脚锁定可能暂时放松。", "INFO")
    if selected_action is not None and selected_action.get("baw_seam_smoothing_enabled"):
        remap.label(text="当前动作：已应用实验防接缝突变", icon="CHECKMARK")
    elif selected_action is not None:
        skipped = {"NO_ADJACENT_CLIP": "未应用防突变：无相邻前段",
                   "CLIP_TOO_SHORT": "未应用防突变：片段过短",
                   "NO_COMMON_CHANNELS": "未应用防突变：无共同骨骼通道"}
        reason = skipped.get(selected_action.get("baw_seam_smoothing_status", ""))
        if reason:
            remap.label(text=reason, icon="INFO")

    target = settings.reuse_target_rig
    source_owner = str(selected_action.get("bam_target_object", "") or "") if selected_action else ""
    same_model = bool(selected_action and target and source_owner == target.name)
    ready = selected_action is not None and target is not None
    primary = remap.column()
    primary.enabled = ready
    primary.scale_y = 1.35
    if same_model:
        replace_button = primary.operator(
            "baw.auto_remap_existing",
            text="重新映射并替换所选动作",
            icon="FILE_REFRESH",
        )
        replace_button.action_name = selected_action.name
        remap.label(text="原动作会自动保留为备份", icon="INFO")
    else:
        import_one_button = primary.operator(
            "baw.auto_import_existing",
            text="导入所选动作",
            icon="IMPORT",
        )
        import_one_button.action_name = selected_action.name if selected_action is not None else ""
        animation = getattr(target, "animation_data", None) if target is not None else None
        target_has_motion = bool(
            animation
            and (
                animation.action is not None
                or any(strip.action is not None for track in animation.nla_tracks for strip in track.strips)
            )
        )
        if ready and source_owner and not target_has_motion:
            batch = remap.column()
            batch.scale_y = 1.1
            batch_button = batch.operator(
                "baw.auto_import_all_existing",
                text="导入来源模型全部动作",
                icon="NLA",
            )
            batch_button.action_name = selected_action.name
            remap.label(text="全部导入会按时间轴重建片段与衔接", icon="INFO")


def _draw_auto_mode(layout, context) -> None:
    settings = context.scene.baw_auto_director
    proscenium = getattr(context.scene, "proscenium", None)
    bridge = _bridge_settings(context)

    inputs = layout.box()
    inputs.label(text="当前 Clip", icon="ARMATURE_DATA")
    inputs.prop(settings, "target_rig", text="角色骨架")
    inputs.template_ID(
        settings,
        "prompt_text",
        new="baw.auto_prompt_new",
        unlink="baw.auto_prompt_unlink",
    )
    prompt = getattr(settings, "prompt_text", None)
    button_text = "打开多行提示词编辑器" if prompt else "新建并打开多行提示词"
    inputs.operator("baw.auto_prompt_edit", text=button_text, icon="TEXT")
    if prompt is not None:
        content = prompt.as_string()
        line_count = len(content.splitlines()) if content else 0
        count=len(content.strip())
        _wrapped(inputs, context, f"{prompt.name} · {line_count} 行 · {count}/1000 字符", "ERROR" if count>1000 else "FILE_TEXT")
    else:
        _wrapped(inputs, context, "只粘贴当前 Clip 的英文动作内容；关键帧与约束请单独设置。", "INFO")
    _wrapped(inputs, context, "每次只输入并生成一个 Clip；检查通过后，再把时间轴移到下一段起点。", "INFO")
    inputs.prop(settings, "total_frames")
    fps=context.scene.render.fps/context.scene.render.fps_base
    inputs.label(text=f"沿用场景 {fps:g} FPS · {settings.total_frames/fps:.2f} 秒")

    status = layout.box()
    status.alert = settings.status_level == "ERROR"
    icon = "ERROR" if settings.status_level == "ERROR" else (
        "CHECKMARK" if settings.status_level == "READY" else "INFO"
    )
    _wrapped(status, context, settings.status_message, icon)
    if settings.state == "RUNNING":
        status.progress(
            factor=settings.progress,
            type="BAR",
            text=f"处理中 · {round(settings.progress * 100)}%",
        )
        _primary(status, "baw.auto_cancel", "取消当前生成", "CANCEL")
    elif (
        settings.state == "PREVIEW_READY"
        and bool(proscenium and getattr(proscenium, "is_previewing", False))
    ):
        _primary(status, "baw.auto_finalize_preview", "接受预览并输出到角色", "CHECKMARK")
        status.label(text="确认后将生成角色独立 Action", icon="ACTION")
    else:
        _primary(status, "baw.auto_run", "生成当前 Clip 动作", "PLAY")
        status.label(text="单段设置 → AI 动作 → 角色输出", icon="FORWARD")

    _draw_action_reuse(layout, context, settings)

    layout.prop(settings, "show_advanced", text="高级设置与辅助操作", toggle=True, icon="PREFERENCES")
    if not settings.show_advanced:
        return

    advanced = layout.box()
    advanced.label(text="动作设置", icon="SETTINGS")
    advanced.prop(settings, "root_motion")
    if bridge is not None and hasattr(bridge, "motion_space"):
        advanced.prop(bridge, "motion_space", text="动作空间")
    if bridge is not None and hasattr(bridge, "use_end_effector_guard"):
        guard = advanced.row(align=True)
        guard.prop(bridge, "use_end_effector_guard", text="末端防穿插")
        if bridge.use_end_effector_guard and hasattr(bridge, "end_effector_guard_strength"):
            guard.prop(bridge, "end_effector_guard_strength", text="幅度")
    advanced.prop(settings, "preroll_margin")
    _wrapped(
        advanced,
        context,
        "全部负滚动帧都用于从初始姿态平滑进入动作首姿，不再设置独立静置段。",
        "TIME",
    )
    advanced.prop(settings, "seed")
    advanced.prop(settings, "auto_accept_motion")
    _wrapped(
        advanced,
        context,
        "无已有动作或位于时间轴起始时使用平滑过渡；已有动作时把角色当前姿态固定为新 Clip 首帧。",
        "INFO",
    )

    outputs = layout.box()
    outputs.label(text="可选 · 场景辅助", icon="SCENE_DATA")
    _wrapped(outputs, context, "默认全部关闭，只生成角色动作。", "INFO")
    outputs.prop(settings, "build_set")
    if settings.build_set:
        outputs.prop(settings, "environment")
    outputs.prop(settings, "build_lighting")
    if settings.build_lighting:
        outputs.prop(settings, "lighting")
    outputs.prop(settings, "build_camera")

    tools = advanced.column(align=True)
    tools.operator("baw.auto_compile_plan", text="只生成导演方案", icon="TEXT")
    scene_tool = tools.row()
    scene_tool.enabled = settings.build_set or settings.build_lighting or settings.build_camera
    scene_tool.operator("baw.auto_build_scene", text="只刷新勾选的场景内容", icon="SCENE_DATA")
    if settings.generated_object_count:
        tools.operator("baw.auto_clear_scene", text="清除自动导演场景", icon="TRASH")
    if settings.plan_json:
        _wrapped(
            advanced,
            context,
            f"当前方案：{settings.last_timing_summary}；{settings.last_environment} / {settings.last_lighting}；"
            f"受控对象 {settings.generated_object_count} 个。{settings.last_start_summary}",
            "PRESET",
        )


def _draw_project_stage(layout, context) -> None:
    settings = context.scene.baw_settings
    box = layout.box()
    box.label(text="工程准备", icon="FILE_FOLDER")
    box.prop(settings, "project_root")
    _primary(box, "baw.initialize_workflow", "初始化工程目录与场景", "NEWFOLDER")
    _wrapped(box, context, "创建固定项目目录和带所有权标记的场景集合；不会覆盖已有文件。", "LOCKED")
    _wrapped(box, context, settings.last_workflow_summary, "INFO")


def _draw_motion_stage(layout, context) -> None:
    status = external_addon_status()
    bridge = _bridge_settings(context)
    box = layout.box()
    box.label(text="AI 动作与角色输出", icon="ARMATURE_DATA")
    if not _component_ready("Proscenium", status):
        box.label(text="Proscenium 未就绪", icon="ERROR")
        _wrapped(box, context, "启用 Proscenium，完成登录并连接服务后再生成动作。")
        return
    if not _component_ready("Proscenium Motion Bridge", status) or bridge is None:
        box.label(text="Proscenium Motion Bridge 未就绪", icon="ERROR")
        return

    box.prop(bridge, "target_rig", text="角色目标骨架")
    if hasattr(bridge, "root_motion_policy"):
        box.prop(bridge, "root_motion_policy", text="整体位移")
    if hasattr(bridge, "motion_space"):
        box.prop(bridge, "motion_space", text="动作空间")
    if hasattr(bridge, "use_end_effector_guard"):
        guard = box.row(align=True)
        guard.prop(bridge, "use_end_effector_guard", text="末端防穿插")
        if bridge.use_end_effector_guard and hasattr(bridge, "end_effector_guard_strength"):
            guard.prop(bridge, "end_effector_guard_strength", text="幅度")
    _primary(box, "ba_motion_bridge.accept_and_retarget", "接受预览并输出角色动作", "ACTION")
    _wrapped(
        box,
        context,
        "请先在 Proscenium 中生成预览。本按钮会自动识别官方源骨架、检查映射并生成独立 Action。",
        "INFO",
    )
    status_row = box.box()
    status_row.alert = getattr(bridge, "status_level", "INFO") == "ERROR"
    _wrapped(
        status_row,
        context,
        bridge.status_message,
        "ERROR" if status_row.alert else "INFO",
    )
    if bridge.last_output_action:
        result = box.box()
        _wrapped(result, context, f"上次输出：{bridge.last_output_action}", "ACTION")
        if _has_operator("ba_motion_bridge.activate_output"):
            result.operator(
                "ba_motion_bridge.activate_output",
                text="重新激活并预热物理",
                icon="PLAY",
            )
    if (
        bridge.constraint_snapshot_json or bridge.previous_target_state_available
    ) and _has_operator("ba_motion_bridge.restore_previous_state"):
        box.operator(
            "ba_motion_bridge.restore_previous_state",
            text="恢复输出前的角色状态",
            icon="LOOP_BACK",
        )


def _draw_cleanup_stage(layout, context) -> None:
    settings = context.scene.baw_settings
    box = layout.box()
    box.label(text="动作清理与人工修正", icon="FCURVE")
    box.prop(settings, "cleanup_profile", expand=True)
    box.prop(
        settings,
        "show_cleanup_parameters",
        text="显示清理参数",
        toggle=True,
        icon="SETTINGS",
    )
    if settings.show_cleanup_parameters:
        details = box.column(align=True)
        details.prop(settings, "smooth_strength")
        details.prop(settings, "smooth_passes")
        details.prop(settings, "simplify_tolerance")
    _primary(box, "baw.clean_mocap_action", "复制原动作并清理曲线", "FCURVE")
    box.label(text="原动作保留不变；四元数旋转不会被平滑", icon="LOCKED")
    _primary(box, "baw.create_correction_layer", "建立非破坏人工修正层", "NLA")
    box.label(text="只在新 CORR Action 中记录手工修正", icon="INFO")
    _wrapped(box, context, settings.last_clean_summary, "INFO")


def _draw_shot_stage(layout, context) -> None:
    settings = context.scene.baw_settings
    status = external_addon_status()
    box = layout.box()
    box.label(text="镜头", icon="CAMERA_DATA")
    box.prop(settings, "shot_type")
    _primary(box, "baw.create_camera_rig", "按角色尺寸创建镜头", "CAMERA_DATA")
    box.label(text="自动创建目标点、焦距和景深；再次运行会更新现有镜头", icon="INFO")
    if context.scene.camera is not None:
        box.operator("baw.add_camera_cut", text="当前帧添加切镜标记", icon="MARKER")

    lights = layout.box()
    lights.label(text="灯光", icon="LIGHT_AREA")
    lights.prop(settings, "light_power")
    _primary(lights, "baw.create_light_rig", "按角色尺寸创建三点光", "LIGHT_AREA")
    lights.label(text="生成主光、补光和轮廓光；保留用户已有 World", icon="INFO")

    if _component_ready("Add Camera Rigs", status):
        pro = layout.box()
        pro.label(text="可选 · 专业相机 Rig", icon="CON_CAMERASOLVER")
        pro.prop(settings, "camera_rig_mode")
        pro.operator("baw.create_pro_camera_rig", text="创建所选专业 Rig", icon="CON_CAMERASOLVER")


def _draw_delivery_stage(layout, context) -> None:
    settings = context.scene.baw_settings
    box = layout.box()
    box.label(text="预览与交付", icon="OUTPUT")
    _primary(box, "baw.prepare_preview", "设置 720p 快速预览", "OUTPUT")
    box.label(text="设置 Eevee、30 FPS、H.264 和项目预览路径", icon="INFO")
    _primary(box, "baw.audit", "运行交付检查", "CHECKMARK")
    box.label(text="检查动作、相机、灯光、贴图和输出设置", icon="INFO")
    _wrapped(box, context, settings.last_audit_summary, "INFO")

    layout.prop(
        settings,
        "show_delivery_maintenance",
        text="安全清理",
        toggle=True,
        icon="TRASH",
    )
    if settings.show_delivery_maintenance:
        clean = layout.box()
        clean.operator(
            "baw.cleanup_bridge_temporary",
            text="清理 Bridge 临时资源",
            icon="TRASH",
        )
        clean.operator("baw.cleanup_cache", text="清理工作台生成缓存", icon="TRASH")
        _wrapped(clean, context, "只处理带所有权标记的临时数据；不会删除模型、贴图或输出 Action。", "LOCKED")


def _draw_legacy_stage(layout, context) -> None:
    box = layout.box()
    box.label(text="传统视频动捕 · BlendCap → MMD", icon="TRACKING")
    _wrapped(box, context, "仅用于传统 BlendCap/BVH；Proscenium 官方 SOMA 动作不要走此入口。", "INFO")
    scene = context.scene
    if not hasattr(bpy.types.Scene, "blendcap_retarget_source"):
        box.label(text="BlendCap 未启用", icon="ERROR")
        return
    if not _has_operator("blendcap_motion_bridge.detect"):
        box.label(text="BlendCap Motion Bridge 未启用", icon="ERROR")
        return
    box.prop(scene, "blendcap_retarget_source", text="BVH 来源")
    box.prop(scene, "blendcap_retarget_target", text="MMD 目标")
    if _has_operator("blendcap_motion_bridge.quick_retarget"):
        _primary(box, "blendcap_motion_bridge.quick_retarget", "自动准备并安全重定向", "ACTION")
        box.label(text="自动检测、加载映射并写入负帧预滚动", icon="INFO")
    else:
        box.operator("blendcap_motion_bridge.detect", text="检测骨骼映射")
        box.operator("blendcap_motion_bridge.write_preset", text="写入并加载映射 preset")


def _draw_manual_mode(layout, context) -> None:
    settings = context.scene.baw_settings
    layout.prop(settings, "manual_stage", text="当前制作阶段")
    drawers = {
        "PROJECT": _draw_project_stage,
        "MOTION": _draw_motion_stage,
        "CLEANUP": _draw_cleanup_stage,
        "SHOT": _draw_shot_stage,
        "DELIVERY": _draw_delivery_stage,
        "LEGACY": _draw_legacy_stage,
    }
    drawers[settings.manual_stage](layout, context)


def _draw_diagnostics(layout, context) -> None:
    settings = context.scene.baw_settings
    layout.prop(
        settings,
        "show_diagnostics",
        text="组件诊断",
        toggle=True,
        icon="TOOL_SETTINGS",
    )
    if not settings.show_diagnostics:
        return
    status = external_addon_status()
    box = layout.box()
    for name, enabled in status.items():
        ready = _component_ready(name, status)
        state = "就绪" if ready else ("已启用但未就绪" if enabled else "未检测")
        box.label(
            text=f"{name} · {state}",
            icon="CHECKMARK" if ready else "ERROR",
        )


class BAW_PT_main(bpy.types.Panel):
    bl_idname = "BAW_PT_main"
    bl_label = "一站式角色动画"
    bl_category = "BA 动画"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.baw_settings
        status = external_addon_status()
        core = ("MMD Tools", "Proscenium", "Proscenium Motion Bridge")
        ready_count = sum(_component_ready(name, status) for name in core)

        header = layout.box()
        header.label(text="BA 动画工作台 0.10.0", icon="ANIM")
        header.label(
            text=f"核心 {ready_count}/{len(core)}",
            icon="CHECKMARK" if ready_count == len(core) else "ERROR",
        )
        header.prop(settings, "workspace_mode", expand=True)

        if settings.workspace_mode == "AUTO":
            _draw_auto_mode(layout, context)
        else:
            _draw_manual_mode(layout, context)

        _draw_diagnostics(layout, context)


CLASSES = (BAW_PT_main,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
