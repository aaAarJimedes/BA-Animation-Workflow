from __future__ import annotations

import json
import math
import re
import time
import uuid

import bpy
from bpy.app.handlers import persistent
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from mathutils import Matrix, Quaternion, Vector

from .constants import ROLE_KEY, SCENE_ID_KEY
from .utils import (
    ensure_scene_collections,
    ensure_scene_id,
    find_armature,
    is_owned,
    mark_owned,
    object_bounds_world,
    point_at,
)


PLAN_SCHEMA = 4
PLAN_TEXT_ROLE = "AUTO_DIRECTOR_PLAN"
AUTO_ROLE_PREFIX = "AUTO_DIRECTOR::"
CANONICAL_MODEL_KEY = "proscenium_canonical_model"
CANONICAL_MODEL_ID = "kimodo-soma-rp"
TEXT_ACTION_LINK_VERSION = 4
_POSE_CURVE_RE = re.compile(
    r'^pose\.bones\["((?:\\.|[^"\\])*)"\]\.'
    r'(location|rotation_quaternion|rotation_euler|rotation_axis_angle|scale)$'
)


ENVIRONMENT_ITEMS = (
    ("AUTO", "自动判断", "根据创作描述选择最接近的实验场景模板"),
    ("STUDIO", "摄影棚", "干净背景与柔和地面，适合角色展示"),
    ("CLASSROOM", "教室", "课桌、黑板和室内日光氛围"),
    ("STREET", "街道", "城市体块、路面与可选霓虹氛围"),
    ("STAGE", "舞台", "抬高舞台和表演背景板"),
    ("OUTDOOR", "户外", "开阔地面和抽象自然体块"),
)

LIGHTING_ITEMS = (
    ("AUTO", "自动判断", "根据描述和场景模板选择灯光气氛"),
    ("NEUTRAL", "中性", "清楚稳定的三点光"),
    ("WARM", "暖色", "偏日落或温馨气氛"),
    ("COOL", "冷色", "偏月光、夜景或科技气氛"),
    ("DRAMATIC", "戏剧", "更强的明暗与轮廓对比"),
    ("DAYLIGHT", "日光", "明亮自然的室外或窗光感"),
)

ROOT_MOTION_ITEMS = (
    ("AUTO", "跟随 Proscenium", "沿用 Proscenium 的原地动作开关"),
    ("FULL", "完整位移", "保留角色的水平移动与上下起伏"),
    ("IN_PLACE", "原地动作", "只保留身体表演，不传递整体位移"),
)


def _poll_armature(self, obj):
    if obj is None or obj.type != "ARMATURE":
        return False
    scene = getattr(self, "id_data", None)
    return not isinstance(scene, bpy.types.Scene) or obj.name in scene.objects


def _is_retarget_output_action(action) -> bool:
    return bool(
        action is not None
        and action.get("bam_role") == "RETARGET_OUTPUT"
        and not action.get("baw_replaced_by")
    )


def _is_proscenium_source_action(action) -> bool:
    return bool(
        action is not None
        and action.name.startswith("Proscenium_Motion:")
        and action.name != "Proscenium_Motion: Preview"
        and not action.get("baw_replaced_by")
    )


def _is_orphan_source_action(action) -> bool:
    if not _is_proscenium_source_action(action):
        return False
    return not any(
        _is_retarget_output_action(candidate)
        and str(candidate.get("baw_source_action", "") or "") == action.name
        for candidate in bpy.data.actions
    )


def _poll_retarget_action(self, action):
    return _is_retarget_output_action(action) or _is_orphan_source_action(action)


def _poll_reuse_text(_self, text):
    return bool(
        text is not None
        and text.get(ROLE_KEY) != PLAN_TEXT_ROLE
        and _prompt_key(text.as_string())
    )


def _update_remap_action(self, context):
    if getattr(self, "remap_prompt_syncing", False):
        return
    action = getattr(self, "remap_action", None)
    if action is None:
        self.remap_prompt_syncing = True
        try:
            self.remap_prompt_text = None
        finally:
            self.remap_prompt_syncing = False
        return
    try:
        _source_action, prompt_text = _resolve_action_link(
            context.scene,
            self,
            action,
            persist=True,
        )
    except (AttributeError, RuntimeError, TypeError, ValueError):
        prompt_text = None
    self.remap_prompt_syncing = True
    try:
        self.remap_prompt_text = prompt_text
    finally:
        self.remap_prompt_syncing = False


def _update_remap_prompt_text(self, context):
    if getattr(self, "remap_prompt_syncing", False):
        return
    text = getattr(self, "remap_prompt_text", None)
    action = None
    if text is not None:
        try:
            action = _resolve_text_action(
                context.scene,
                self,
                text,
                target=getattr(self, "reuse_target_rig", None),
                persist=True,
            )
        except (AttributeError, RuntimeError, TypeError, ValueError):
            action = None
    self.remap_prompt_syncing = True
    try:
        self.remap_action = action
    finally:
        self.remap_prompt_syncing = False
    if action is not None and text is not None and getattr(self, "state", "") != "RUNNING":
        _show_reuse_clip(context, self, text, action)


def _show_reuse_clip(context, settings, text, action):
    """Focus one linked take without losing the previously active take."""
    scene = context.scene
    start, end = _clip_motion_bounds(action)
    target = getattr(settings, "reuse_target_rig", None) or getattr(settings, "target_rig", None)
    if target is not None and _action_target_name(action) == target.name:
        animation = target.animation_data_create()
        previous = animation.action
        # An active take has no NLA strip yet. Preserve its entire playback
        # range before switching backwards/forwards, never trim to selection.
        if previous is not None and previous != action:
            represented = any(strip.action == previous for track in animation.nla_tracks for strip in track.strips)
            if not represented:
                lo, hi = (float(v) for v in previous.frame_range)
                if hi > lo:
                    track = animation.nla_tracks.new()
                    track.name = f"BAW_上一段_{previous.name}"
                    strip = track.strips.new(previous.name, int(math.floor(lo)), previous)
                    strip.action_frame_start, strip.action_frame_end = lo, hi
                    strip.frame_start, strip.frame_end = lo, hi
                    strip.extrapolation = "NOTHING"
                    strip.blend_type = "REPLACE"
            previous.use_fake_user = True
        animation.action = action
        animation.action_blend_type = "REPLACE"
        animation.action_extrapolation = "NOTHING"
        animation.action_influence = 1.0
        animation.use_nla = True
        if target.name in context.view_layer.objects:
            context.view_layer.objects.active = target
            target.select_set(True)
    props = getattr(scene, "proscenium", None)
    if props is not None:
        matches = [i for i, block in enumerate(props.prompt_blocks)
                   if (block.frame_start, block.frame_end) == (start, end)]
        index = matches[0] if matches else len(props.prompt_blocks)
        block = props.prompt_blocks[index] if matches else props.prompt_blocks.add()
        block.frame_start, block.frame_end = start, end
        block.prompt = text.as_string()
        block.enabled = True
        props.active_block_index = index
    scene.frame_start = min(scene.frame_start, start)
    scene.frame_end = max(scene.frame_end, end)
    scene.frame_set(start)
    for area in getattr(getattr(context, "screen", None), "areas", ()):
        if area.type == "TEXT_EDITOR":
            area.spaces.active.text = text
        area.tag_redraw()


def _sync_reuse_selection(scene) -> None:
    settings = getattr(scene, "baw_auto_director", None)
    if settings is None:
        return
    _repair_owned_nla_clip_references(scene)
    text = getattr(settings, "remap_prompt_text", None)
    if text is None:
        return
    try:
        action = _resolve_text_action(
            scene,
            settings,
            text,
            target=getattr(settings, "reuse_target_rig", None),
            persist=True,
        )
    except (AttributeError, RuntimeError, TypeError, ValueError):
        action = None
    settings.remap_prompt_syncing = True
    try:
        settings.remap_action = action
    finally:
        settings.remap_prompt_syncing = False


@persistent
def _sync_reuse_selection_on_load(_unused):
    for scene in bpy.data.scenes:
        _sync_reuse_selection(scene)


class BAW_PG_auto_director(bpy.types.PropertyGroup):
    target_rig: PointerProperty(
        name="角色骨架",
        description="用户提供模型中的目标人体骨架；未指定时使用当前活动骨架",
        type=bpy.types.Object,
        poll=_poll_armature,
    )
    creative_prompt: StringProperty(
        name="兼容短提示",
        description="旧工程兼容字段；创建多行提示词后，工作流将优先使用 Blender 文本块",
        default="角色从容地向前走两步，停下并看向镜头；干净摄影棚，柔和电影灯光",
        maxlen=65535,
    )
    prompt_text: PointerProperty(
        name="当前 Clip 多行提示词",
        description="Blender 文本块；全部内容作为一个动作段提交，不再解析内部时间结构",
        type=bpy.types.Text,
    )
    environment: EnumProperty(name="场景模板", items=ENVIRONMENT_ITEMS, default="AUTO")
    lighting: EnumProperty(name="灯光气氛", items=LIGHTING_ITEMS, default="AUTO")
    root_motion: EnumProperty(name="整体位移", items=ROOT_MOTION_ITEMS, default="AUTO")
    total_frames: IntProperty(
        name="当前 Clip 总帧数",
        description="从当前时间轴帧开始生成的单段动作总帧数",
        default=150,
        min=2,
        max=10000,
    )
    seed: IntProperty(name="随机种子", default=42, min=0, max=999999)
    preroll_margin: IntProperty(
        name="负滚动过渡边距（帧）",
        description="无已有动作或从时间轴起始帧生成时，从初始姿态平滑进入动作首姿的帧数",
        default=60,
        min=0,
        max=1000,
    )
    build_set: BoolProperty(name="自动搭建场景", default=False)
    build_lighting: BoolProperty(name="自动布光", default=False)
    build_camera: BoolProperty(name="自动构图", default=False)
    auto_accept_motion: BoolProperty(
        name="生成后自动接受并输出",
        description="开启后，生成成功会接受 Proscenium 预览并立即重定向到角色；点击运行即确认此选择",
        default=True,
    )
    show_advanced: BoolProperty(name="显示高级设置", default=False)
    remap_action: PointerProperty(
        name="已生成动作",
        description="选择已输出的角色动作，或生成成功但尚未映射到角色的 Proscenium 源动作",
        type=bpy.types.Action,
        poll=_poll_retarget_action,
        update=_update_remap_action,
    )
    remap_prompt_text: PointerProperty(
        name="动作文本块",
        description="选择文本块后同步关联 Action、时间轴提示词与起始帧；切换时保留其他片段，旧工程仅在可信匹配时修复关联",
        type=bpy.types.Text,
        poll=_poll_reuse_text,
        update=_update_remap_prompt_text,
    )
    remap_prompt_syncing: BoolProperty(default=False, options={"HIDDEN", "SKIP_SAVE"})
    reuse_target_rig: PointerProperty(
        name="导入目标模型",
        description="接收复用动作的新角色骨架；导入不会修改来源模型及其旧 Action",
        type=bpy.types.Object,
        poll=_poll_armature,
    )
    reuse_foot_contact: BoolProperty(
        name="实验：防脚滑",
        description="仅作用于动作复用的重新映射/导入：统一根运动朝向，在参考脚静止且低位时锁定支撑脚；默认关闭。更改后需再次执行，可开关对比；不影响生成流程，目前仅支持 MMD",
        default=False,
    )
    reuse_seam_smoothing: BoolProperty(
        name="实验：防接缝突变",
        description="仅动作复用：平滑相邻片段的姿态与速度。仅当前段保护前段；前后均分会修改两段接缝窗口并成对备份。开关或切换方式后需再次映射",
        default=False,
    )
    reuse_seam_mode: EnumProperty(
        name="过渡方式",
        items=[('CURRENT', '仅当前段', '只平滑当前段开头，保护已确认的前段'),
               ('SPLIT', '前后均分', '总窗口平均分配到前段末尾和当前段开头，奇数多一帧给当前段；两段成对备份')],
        default='CURRENT',
    )
    reuse_seam_frames: IntProperty(
        name="接缝过渡帧数",
        description="整个接缝窗口的总长度，不是每段各自长度。均分模式会影响前段末尾；无相邻前段时跳过。更长窗口更柔和但影响节奏",
        default=10, min=4, max=60,
    )
    state: StringProperty(default="IDLE", options={"HIDDEN", "SKIP_SAVE"})
    status_level: StringProperty(default="INFO", options={"HIDDEN", "SKIP_SAVE"})
    status_message: StringProperty(default="等待生成导演方案", options={"HIDDEN", "SKIP_SAVE"})
    progress: FloatProperty(default=0.0, min=0.0, max=1.0, options={"HIDDEN", "SKIP_SAVE"})
    cancel_requested: BoolProperty(default=False, options={"HIDDEN", "SKIP_SAVE"})
    plan_json: StringProperty(default="", options={"HIDDEN"})
    plan_text_name: StringProperty(default="", options={"HIDDEN"})
    last_environment: StringProperty(default="", options={"HIDDEN"})
    last_lighting: StringProperty(default="", options={"HIDDEN"})
    last_timing_summary: StringProperty(default="", options={"HIDDEN"})
    last_start_summary: StringProperty(default="", options={"HIDDEN"})
    start_behavior: StringProperty(default="", options={"HIDDEN", "SKIP_SAVE"})
    motion_start_frame: IntProperty(default=1, options={"HIDDEN", "SKIP_SAVE"})
    preroll_start_frame: IntProperty(default=1, options={"HIDDEN", "SKIP_SAVE"})
    continuity_pose_json: StringProperty(default="", options={"HIDDEN", "SKIP_SAVE"})
    previous_clip_action: PointerProperty(
        type=bpy.types.Action,
        options={"HIDDEN", "SKIP_SAVE"},
    )
    previous_clip_action_name: StringProperty(default="", options={"HIDDEN", "SKIP_SAVE"})
    previous_clip_use_nla: BoolProperty(default=False, options={"HIDDEN", "SKIP_SAVE"})
    timeline_before_json: StringProperty(default="", options={"HIDDEN", "SKIP_SAVE"})
    generated_object_count: IntProperty(default=0, min=0, options={"HIDDEN"})
    previous_world: PointerProperty(type=bpy.types.World, options={"HIDDEN"})
    previous_camera: PointerProperty(type=bpy.types.Object, options={"HIDDEN"})


def _keyword_score(text: str, keywords: tuple[str, ...]) -> int:
    return sum(1 for keyword in keywords if keyword in text)


def _choose_environment(prompt: str, requested: str) -> str:
    if requested != "AUTO":
        return requested
    text = prompt.casefold()
    candidates = {
        "CLASSROOM": ("教室", "学校", "课桌", "黑板", "classroom", "school", "desk"),
        "STREET": ("街", "城市", "巷", "霓虹", "夜景", "street", "city", "alley", "neon"),
        "STAGE": ("舞台", "演出", "演唱", "聚光", "stage", "concert", "performance"),
        "OUTDOOR": ("户外", "森林", "公园", "草地", "天空", "outdoor", "forest", "park", "field"),
        "STUDIO": ("摄影棚", "棚拍", "纯色", "studio", "clean backdrop"),
    }
    scores = {name: _keyword_score(text, words) for name, words in candidates.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "STUDIO"


def _choose_lighting(prompt: str, environment: str, requested: str) -> str:
    if requested != "AUTO":
        return requested
    text = prompt.casefold()
    candidates = {
        "WARM": ("温暖", "暖色", "日落", "黄昏", "warm", "sunset", "golden"),
        "COOL": ("冷色", "月光", "夜", "霓虹", "科技", "cool", "moon", "night", "neon"),
        "DRAMATIC": ("戏剧", "紧张", "战斗", "悬疑", "dramatic", "tense", "fight"),
        "DAYLIGHT": ("日光", "晴天", "明亮", "白天", "daylight", "sunny", "bright"),
        "NEUTRAL": ("中性", "柔和", "清楚", "neutral", "soft", "clean"),
    }
    scores = {name: _keyword_score(text, words) for name, words in candidates.items()}
    best = max(scores, key=scores.get)
    if scores[best] > 0:
        return best
    if environment == "STREET":
        return "COOL"
    if environment in {"CLASSROOM", "OUTDOOR"}:
        return "DAYLIGHT"
    if environment == "STAGE":
        return "DRAMATIC"
    return "NEUTRAL"


def _choose_shot(prompt: str) -> str:
    text = prompt.casefold()
    if _keyword_score(text, ("奔跑", "跑", "跳", "战斗", "舞", "run", "jump", "fight", "dance")):
        return "ACTION"
    if _keyword_score(text, ("特写", "表情", "看向镜头", "说话", "close-up", "face", "portrait")):
        return "CLOSE"
    return "FULL"


def _bridge_plan_settings(settings) -> dict:
    scene = getattr(settings, "id_data", None)
    bridge = getattr(scene, "ba_motion_bridge_settings", None) if scene is not None else None
    return {
        "motion_space": getattr(bridge, "motion_space", "TARGET_PLACEMENT"),
        "end_effector_guard": bool(getattr(bridge, "use_end_effector_guard", True)),
        "end_effector_guard_strength": float(
            getattr(bridge, "end_effector_guard_strength", 1.0)
        ),
    }


def _prompt_value(settings) -> str:
    text = getattr(settings, "prompt_text", None)
    if text is not None:
        return text.as_string().strip()
    return settings.creative_prompt.strip()


def _new_prompt_text(settings):
    text = bpy.data.texts.new("BAW_当前Clip提示词")
    legacy = settings.creative_prompt.strip()
    if legacy:
        text.write(legacy)
    text.use_fake_user = True
    settings.prompt_text = text
    return text


def compile_plan(settings, placement_frame: int | None = None) -> dict:
    prompt = _prompt_value(settings)
    if not prompt:
        raise ValueError("请先输入当前 Clip 的动作描述")
    if len(prompt) > 1000:
        raise ValueError("当前 Clip 提示词超过 Proscenium 的 1000 字符上限；请精简为一个动作段")
    scene = getattr(settings, "id_data", None)
    render = getattr(scene, "render", None)
    if render is not None:
        fps = int(round(float(render.fps) / max(float(render.fps_base), 1e-6)))
    else:
        fps = int(getattr(settings, "fps", 30))
    frame_count = int(settings.total_frames)
    frame_start = int(placement_frame) if placement_frame is not None else 1
    frame_end = frame_start + frame_count - 1
    environment = _choose_environment(prompt, settings.environment)
    lighting = _choose_lighting(prompt, environment, settings.lighting)
    block = {"prompt": prompt, "frame_start": frame_start, "frame_end": frame_end}
    prompt_blocks = [{**block, "batch": 1}]
    batches = [{
        "index": 1,
        "title": "当前 Clip",
        "local_frame_start": frame_start,
        "local_frame_end": frame_end,
        "global_frame_start": frame_start,
        "global_frame_end": frame_end,
        "authored_frame_start": 1,
        "authored_frame_end": frame_count,
        "prompt_blocks": [block],
        "pose_anchors": [],
        "root_motion": settings.root_motion,
    }]
    timing_summary = f"{fps} FPS · {frame_count} 帧 · 1 个动作段"
    return {
        "schema": PLAN_SCHEMA,
        "run_id": str(uuid.uuid4()),
        "prompt": prompt,
        "prompt_source": "TEXT" if getattr(settings, "prompt_text", None) is not None else "LEGACY",
        "fps": fps,
        "frame_start": frame_start,
        "frame_end": frame_end,
        "frame_count": frame_count,
        "duration_seconds": frame_count / fps,
        "seed": int(settings.seed),
        "environment": environment,
        "lighting": lighting,
        "shot": _choose_shot(prompt),
        "root_motion": settings.root_motion,
        "prompt_blocks": prompt_blocks,
        "pose_anchors": [],
        "generation_batches": batches,
        "timing_sources": {"fps": "SCENE", "frames": "PANEL", "blocks": "SINGLE"},
        "timing_summary": timing_summary,
        "warnings": [],
        "build": {
            "set": bool(settings.build_set),
            "lighting": bool(settings.build_lighting),
            "camera": bool(settings.build_camera),
        },
        "bridge": _bridge_plan_settings(settings),
        "auto_accept_motion": bool(settings.auto_accept_motion),
    }


def _plan_text(scene, settings):
    scene_id = ensure_scene_id(scene)
    text = bpy.data.texts.get(settings.plan_text_name) if settings.plan_text_name else None
    if text is None or not is_owned(text, PLAN_TEXT_ROLE, scene_id):
        base_name = "BAW_自动导演方案"
        candidate = bpy.data.texts.get(base_name)
        if candidate is None or is_owned(candidate, PLAN_TEXT_ROLE, scene_id):
            text = candidate or bpy.data.texts.new(base_name)
        else:
            text = bpy.data.texts.new(f"{base_name}_{scene_id[:8]}")
        mark_owned(text, PLAN_TEXT_ROLE, scene_id)
        settings.plan_text_name = text.name
    return text


def write_plan(scene, settings, plan: dict) -> None:
    payload = json.dumps(plan, ensure_ascii=False, indent=2)
    settings.plan_json = payload
    settings.last_environment = plan["environment"]
    settings.last_lighting = plan["lighting"]
    settings.last_timing_summary = plan.get("timing_summary", "")
    text = _plan_text(scene, settings)
    text.clear()
    text.write(payload)


def _auto_role(name: str) -> str:
    return f"{AUTO_ROLE_PREFIX}{name}"


def _is_auto_owned(datablock, scene_id: str) -> bool:
    role = datablock.get(ROLE_KEY, "") if datablock is not None else ""
    return (
        isinstance(role, str)
        and role.startswith(AUTO_ROLE_PREFIX)
        and is_owned(datablock, scene_id=scene_id)
    )


def _remove_auto_objects(scene) -> int:
    scene_id = ensure_scene_id(scene)
    targets = [obj for obj in tuple(bpy.data.objects) if _is_auto_owned(obj, scene_id)]
    owned_data = [obj.data for obj in targets if getattr(obj, "data", None) is not None]
    for obj in targets:
        bpy.data.objects.remove(obj, do_unlink=True)
    for datablock in owned_data:
        if datablock.users != 0 or not _is_auto_owned(datablock, scene_id):
            continue
        if isinstance(datablock, bpy.types.Mesh):
            bpy.data.meshes.remove(datablock)
        elif isinstance(datablock, bpy.types.Light):
            bpy.data.lights.remove(datablock)
        elif isinstance(datablock, bpy.types.Camera):
            bpy.data.cameras.remove(datablock)
    return len(targets)


def clear_generated_scene(scene, settings, restore_context: bool = True) -> int:
    count = _remove_auto_objects(scene)
    if restore_context:
        try:
            previous_camera = settings.previous_camera
        except ReferenceError:
            previous_camera = None
        if previous_camera is not None and previous_camera.name in scene.objects:
            scene.camera = previous_camera
        elif scene.camera is not None and _is_auto_owned(scene.camera, ensure_scene_id(scene)):
            scene.camera = None
        try:
            previous_world = settings.previous_world
        except ReferenceError:
            previous_world = None
        if scene.world is not None and _is_auto_owned(scene.world, ensure_scene_id(scene)):
            scene.world = previous_world
        settings.previous_camera = None
        settings.previous_world = None
    settings.generated_object_count = 0
    return count


def _material(scene, key: str, color: tuple[float, float, float, float], emission: float = 0.0):
    scene_id = ensure_scene_id(scene)
    role = _auto_role(f"MAT::{key}")
    material = next((item for item in bpy.data.materials if is_owned(item, role, scene_id)), None)
    if material is None:
        material = bpy.data.materials.new(f"BAW_AUTO_{key}")
        mark_owned(material, role, scene_id)
    material.diffuse_color = color
    material.use_nodes = True
    principled = material.node_tree.nodes.get("Principled BSDF")
    if principled is not None:
        principled.inputs["Base Color"].default_value = color
        principled.inputs["Roughness"].default_value = 0.55
        if "Emission Color" in principled.inputs:
            principled.inputs["Emission Color"].default_value = color
            principled.inputs["Emission Strength"].default_value = emission
    return material


def _box(scene, collection, name: str, location, dimensions, material=None):
    sx, sy, sz = (max(float(value), 0.001) * 0.5 for value in dimensions)
    vertices = [
        (-sx, -sy, -sz), (sx, -sy, -sz), (sx, sy, -sz), (-sx, sy, -sz),
        (-sx, -sy, sz), (sx, -sy, sz), (sx, sy, sz), (-sx, sy, sz),
    ]
    faces = [
        (0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1),
        (1, 5, 6, 2), (2, 6, 7, 3), (4, 0, 3, 7),
    ]
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    scene_id = ensure_scene_id(scene)
    mark_owned(mesh, _auto_role(f"MESH::{name}"), scene_id)
    obj = bpy.data.objects.new(name, mesh)
    mark_owned(obj, _auto_role(f"OBJECT::{name}"), scene_id)
    obj.location = location
    if material is not None:
        mesh.materials.append(material)
    collection.objects.link(obj)
    return obj


def _palette(lighting: str):
    return {
        "NEUTRAL": ((1.0, 0.92, 0.82), (0.60, 0.75, 1.0), (1.0, 0.55, 0.36), (0.025, 0.03, 0.05, 1.0)),
        "WARM": ((1.0, 0.62, 0.32), (0.55, 0.68, 1.0), (1.0, 0.25, 0.10), (0.06, 0.025, 0.012, 1.0)),
        "COOL": ((0.58, 0.72, 1.0), (0.35, 0.50, 1.0), (1.0, 0.20, 0.55), (0.008, 0.015, 0.05, 1.0)),
        "DRAMATIC": ((1.0, 0.42, 0.22), (0.18, 0.30, 0.65), (0.50, 0.15, 1.0), (0.008, 0.006, 0.015, 1.0)),
        "DAYLIGHT": ((1.0, 0.92, 0.72), (0.62, 0.82, 1.0), (1.0, 0.78, 0.52), (0.08, 0.12, 0.18, 1.0)),
    }[lighting]


def _build_environment(scene, collection, environment: str, center: Vector, height: float):
    floor_z = center.z - height * 0.5
    neutral = _material(scene, "GROUND", (0.075, 0.085, 0.105, 1.0))
    accent = _material(scene, "ACCENT", (0.12, 0.32, 0.65, 1.0), 0.4 if environment == "STREET" else 0.0)
    pale = _material(scene, "PALE", (0.52, 0.56, 0.62, 1.0))
    dark = _material(scene, "DARK", (0.025, 0.032, 0.045, 1.0))
    made = [_box(scene, collection, "BAW_AUTO_Floor", (center.x, center.y, floor_z - height * 0.025), (height * 8.0, height * 8.0, height * 0.05), neutral)]
    if environment == "STUDIO":
        made.append(_box(scene, collection, "BAW_AUTO_Backdrop", (center.x, center.y + height * 2.0, center.z + height), (height * 6.0, height * 0.08, height * 3.0), pale))
    elif environment == "CLASSROOM":
        made.append(_box(scene, collection, "BAW_AUTO_Wall", (center.x, center.y + height * 2.4, center.z + height), (height * 7.0, height * 0.1, height * 3.0), pale))
        made.append(_box(scene, collection, "BAW_AUTO_Blackboard", (center.x, center.y + height * 2.32, center.z + height * 0.65), (height * 2.7, height * 0.08, height * 0.9), dark))
        for index, x in enumerate((-1.4, 0.0, 1.4)):
            made.append(_box(scene, collection, f"BAW_AUTO_Desk_{index}", (center.x + x * height, center.y + height * 1.0, floor_z + height * 0.36), (height * 0.8, height * 0.45, height * 0.12), pale))
    elif environment == "STREET":
        for index, x in enumerate((-2.7, 2.7)):
            made.append(_box(scene, collection, f"BAW_AUTO_Building_{index}", (center.x + x * height, center.y + height * 2.0, floor_z + height * 1.6), (height * 1.8, height * 1.4, height * 3.2), dark))
            made.append(_box(scene, collection, f"BAW_AUTO_Neon_{index}", (center.x + x * height * 0.9, center.y + height * 1.25, center.z + height * 0.55), (height * 0.55, height * 0.06, height * 0.9), accent))
    elif environment == "STAGE":
        made.append(_box(scene, collection, "BAW_AUTO_Stage", (center.x, center.y + height * 0.3, floor_z + height * 0.14), (height * 5.0, height * 3.2, height * 0.28), dark))
        made.append(_box(scene, collection, "BAW_AUTO_StageBack", (center.x, center.y + height * 2.3, center.z + height), (height * 5.5, height * 0.12, height * 3.0), accent))
    elif environment == "OUTDOOR":
        ground = _material(scene, "OUTDOOR", (0.12, 0.23, 0.12, 1.0))
        made[0].data.materials.clear()
        made[0].data.materials.append(ground)
        for index, x in enumerate((-2.3, 2.0, 3.2)):
            made.append(_box(scene, collection, f"BAW_AUTO_Nature_{index}", (center.x + x * height, center.y + height * (1.2 + 0.3 * index), floor_z + height * (0.5 + 0.2 * index)), (height * 0.45, height * 0.45, height * (1.0 + 0.4 * index)), dark))
    return made


def _build_lights(scene, collection, lighting: str, center: Vector, height: float, base_power: float):
    key_color, fill_color, rim_color, world_color = _palette(lighting)
    settings = (
        ("Key", (2.3, -2.4, 3.1), key_color, 1.0, 4.0),
        ("Fill", (-2.7, -1.0, 2.0), fill_color, 0.45, 3.2),
        ("Rim", (1.2, 2.5, 2.8), rim_color, 0.75, 2.5),
    )
    made = []
    scene_id = ensure_scene_id(scene)
    for label, offset, color, factor, size in settings:
        data = bpy.data.lights.new(f"BAW_AUTO_{label}_Data", type="AREA")
        mark_owned(data, _auto_role(f"LIGHT_DATA::{label}"), scene_id)
        data.energy = max(10.0, base_power * factor)
        data.color = color
        data.shape = "DISK"
        data.size = height * size
        obj = bpy.data.objects.new(f"BAW_AUTO_{label}", data)
        mark_owned(obj, _auto_role(f"LIGHT::{label}"), scene_id)
        obj.location = center + Vector(offset) * height
        point_at(obj, center + Vector((0.0, 0.0, height * 0.15)))
        collection.objects.link(obj)
        made.append(obj)

    if scene.world is None or not _is_auto_owned(scene.world, scene_id):
        if scene.world is not None:
            scene.baw_auto_director.previous_world = scene.world
        world = next((item for item in bpy.data.worlds if is_owned(item, _auto_role("WORLD"), scene_id)), None)
        if world is None:
            world = bpy.data.worlds.new("BAW_AUTO_World")
            mark_owned(world, _auto_role("WORLD"), scene_id)
        scene.world = world
    world = scene.world
    world.use_nodes = True
    nodes = world.node_tree.nodes
    background = nodes.get("Background") or nodes.new("ShaderNodeBackground")
    output = nodes.get("World Output") or nodes.new("ShaderNodeOutputWorld")
    surface = output.inputs.get("Surface")
    if surface is not None and not surface.is_linked:
        world.node_tree.links.new(background.outputs["Background"], surface)
    background.inputs["Color"].default_value = world_color
    background.inputs["Strength"].default_value = 0.28 if lighting != "DAYLIGHT" else 0.5
    return made


def _build_camera(scene, settings, collection, shot: str, center: Vector, height: float):
    scene_id = ensure_scene_id(scene)
    if scene.camera is not None and not _is_auto_owned(scene.camera, scene_id) and settings.previous_camera is None:
        settings.previous_camera = scene.camera
    data = bpy.data.cameras.new("BAW_AUTO_Camera_Data")
    mark_owned(data, _auto_role("CAMERA_DATA"), scene_id)
    data.lens = {"CLOSE": 58.0, "ACTION": 40.0, "FULL": 48.0}[shot]
    camera = bpy.data.objects.new("BAW_AUTO_Camera", data)
    mark_owned(camera, _auto_role("CAMERA"), scene_id)
    offset = {
        "CLOSE": (0.0, -2.5, 0.25),
        "ACTION": (2.2, -4.4, 1.1),
        "FULL": (0.0, -4.8, 0.75),
    }[shot]
    camera.location = center + Vector(offset) * height
    target = center + Vector((0.0, 0.0, height * (0.12 if shot != "CLOSE" else 0.28)))
    point_at(camera, target)
    collection.objects.link(camera)
    scene.camera = camera
    return camera


def build_generated_scene(context, plan: dict) -> int:
    scene = context.scene
    settings = scene.baw_auto_director
    target = settings.target_rig or find_armature(context)
    if target is None:
        raise ValueError("请选择用户模型中的角色骨架")
    settings.target_rig = target
    _remove_auto_objects(scene)
    collections = ensure_scene_collections(scene)
    center, height = object_bounds_world(target)
    height = max(height, 0.5)
    made = []
    if plan["build"]["set"]:
        made.extend(_build_environment(scene, collections["BAW_40_STAGE"], plan["environment"], center, height))
    if plan["build"]["lighting"]:
        made.extend(_build_lights(scene, collections["BAW_50_LIGHTS"], plan["lighting"], center, height, scene.baw_settings.light_power))
    if plan["build"]["camera"]:
        made.append(_build_camera(scene, settings, collections["BAW_60_CAMERAS"], plan["shot"], center, height))
    settings.generated_object_count = len(made)
    return len(made)


def _operator_available(path: str) -> bool:
    namespace, name = path.split(".", 1)
    try:
        getattr(getattr(bpy.ops, namespace), name).get_rna_type()
    except (AttributeError, KeyError, RuntimeError):
        return False
    return True


def _set_status(settings, state: str, message: str, level: str = "INFO", progress: float | None = None):
    settings.state = state
    settings.status_level = level
    settings.status_message = message
    if progress is not None:
        settings.progress = max(0.0, min(1.0, float(progress)))
    for window in getattr(bpy.context.window_manager, "windows", ()):
        for area in getattr(window.screen, "areas", ()):
            if area.type == "VIEW_3D":
                area.tag_redraw()


def _resolve_auto_target_switch(context, bridge, target) -> str:
    """Adopt PMB's KEEP protocol before BA starts work on another character."""
    if bridge is None:
        raise RuntimeError("Motion Bridge 场景设置尚未注册")
    if target is None or target.type != "ARMATURE":
        raise RuntimeError("请选择接收动作的角色骨架")
    try:
        previous_target = bridge.previous_target_rig
    except ReferenceError:
        previous_target = None
    target_changed = bool(
        bridge.previous_target_state_available
        and previous_target is not None
        and previous_target != target
    )
    bridge.target_rig = target
    if not target_changed:
        return ""
    if not _operator_available("ba_motion_bridge.resolve_target_switch"):
        raise RuntimeError("Motion Bridge 缺少安全切换模型功能，请更新 Proscenium Motion Bridge")
    result = bpy.ops.ba_motion_bridge.resolve_target_switch("EXEC_DEFAULT", mode="KEEP")
    if result != {"FINISHED"}:
        raise RuntimeError(f"无法结束上一模型 {previous_target.name} 的恢复点：{result}")
    return previous_target.name


def _configure_integrations(context, settings, plan: dict, batch: dict | None = None):
    scene = context.scene
    batch = batch or plan["generation_batches"][0]
    required = (
        "proscenium.connect",
        "proscenium.import_canonical_skeleton",
        "proscenium.generate",
        "ba_motion_bridge.accept_and_retarget",
    )
    missing = [path for path in required if not _operator_available(path)]
    if missing:
        raise RuntimeError("必要组件未就绪：" + "、".join(missing))
    target = settings.target_rig or find_armature(context)
    if target is None or target.type != "ARMATURE":
        raise RuntimeError("请选择用户模型中的角色骨架")
    settings.target_rig = target
    bridge = getattr(scene, "ba_motion_bridge_settings", None)
    proscenium = getattr(scene, "proscenium", None)
    if bridge is None or proscenium is None:
        raise RuntimeError("Proscenium 或 Motion Bridge 场景设置尚未注册")
    _resolve_auto_target_switch(context, bridge, target)
    batch_root_motion = batch.get("root_motion", "AUTO")
    bridge.root_motion_policy = batch_root_motion if batch_root_motion != "AUTO" else plan["root_motion"]
    bridge.accept_preview_on_run = bool(plan["auto_accept_motion"])
    bridge_plan = plan.get("bridge", {})
    if hasattr(bridge, "motion_space"):
        bridge.motion_space = bridge_plan.get("motion_space", bridge.motion_space)
    if hasattr(bridge, "use_end_effector_guard"):
        bridge.use_end_effector_guard = bool(
            bridge_plan.get("end_effector_guard", bridge.use_end_effector_guard)
        )
    if hasattr(bridge, "end_effector_guard_strength"):
        bridge.end_effector_guard_strength = float(
            bridge_plan.get(
                "end_effector_guard_strength", bridge.end_effector_guard_strength
            )
        )

    connect_result = bpy.ops.proscenium.connect("EXEC_DEFAULT")
    if connect_result != {"FINISHED"}:
        raise RuntimeError(f"Proscenium 服务连接失败：{connect_result}")

    source = getattr(proscenium, "target_armature", None)
    if source is None or source.type != "ARMATURE" or source.get(CANONICAL_MODEL_KEY) != CANONICAL_MODEL_ID:
        result = bpy.ops.proscenium.import_canonical_skeleton("EXEC_DEFAULT", with_body=True)
        if result != {"FINISHED"}:
            raise RuntimeError(f"无法导入 Proscenium 官方骨架：{result}")
        source = getattr(proscenium, "target_armature", None)
    if source is None or source == target:
        raise RuntimeError("Proscenium 官方动作骨架未正确建立")

    proscenium.seed = int(plan["seed"])
    proscenium.prompt_blocks.clear()
    for item in batch["prompt_blocks"]:
        block = proscenium.prompt_blocks.add()
        block.prompt = item["prompt"]
        block.frame_start = int(item["frame_start"])
        block.frame_end = int(item["frame_end"])
        block.enabled = True
    scene.render.fps = int(plan["fps"])
    scene.render.fps_base = 1.0
    scene.frame_start = int(batch["local_frame_start"])
    scene.frame_end = int(batch["local_frame_end"])
    return proscenium


def _iter_action_fcurves(action):
    legacy = getattr(action, "fcurves", None)
    if legacy is not None:
        yield from legacy
        return
    for layer in getattr(action, "layers", ()):
        for strip in getattr(layer, "strips", ()):
            for slot in getattr(action, "slots", ()):
                try:
                    channelbag = strip.channelbag(slot)
                except (AttributeError, RuntimeError, TypeError):
                    channelbag = None
                if channelbag is not None:
                    yield from channelbag.fcurves


def _action_bone_channels(action) -> dict[str, set[str]]:
    channels: dict[str, set[str]] = {}
    if action is None:
        return channels
    for curve in _iter_action_fcurves(action):
        match = _POSE_CURVE_RE.fullmatch(curve.data_path)
        if match is None:
            continue
        try:
            bone_name = json.loads(f'"{match.group(1)}"')
        except json.JSONDecodeError:
            continue
        channels.setdefault(bone_name, set()).add(match.group(2))
    return channels


def _timeline_snapshot(scene) -> dict:
    return {
        "fps": int(scene.render.fps),
        "fps_base": float(scene.render.fps_base),
        "frame_start": int(scene.frame_start),
        "frame_end": int(scene.frame_end),
        "frame_current": int(scene.frame_current),
        "use_preview_range": bool(scene.use_preview_range),
        "frame_preview_start": int(scene.frame_preview_start),
        "frame_preview_end": int(scene.frame_preview_end),
    }


def _load_timeline_snapshot(settings) -> dict | None:
    try:
        payload = json.loads(settings.timeline_before_json)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _target_has_motion(target) -> bool:
    animation_data = getattr(target, "animation_data", None)
    if animation_data is None:
        return False
    action = getattr(animation_data, "action", None)
    if action is not None and any(
        len(curve.keyframe_points) > 0 for curve in _iter_action_fcurves(action)
    ):
        return True
    return any(
        getattr(strip, "action", None) is not None
        for track in getattr(animation_data, "nla_tracks", ())
        for strip in track.strips
    )


def _choose_start_behavior(has_motion: bool, current_frame: int, timeline_start: int, margin: int) -> dict:
    motion_start = int(current_frame)
    use_preroll = not has_motion or motion_start <= int(timeline_start)
    return {
        "mode": "PREROLL" if use_preroll else "CURRENT_POSE",
        "motion_start": motion_start,
        "preroll_start": motion_start - max(0, int(margin)) if use_preroll else motion_start,
        "had_existing_motion": bool(has_motion),
    }


def _capture_current_pose(target) -> str:
    bpy.context.view_layer.update()
    evaluated = target.evaluated_get(bpy.context.evaluated_depsgraph_get())
    rows = []
    for bone in target.pose.bones:
        evaluated_bone = evaluated.pose.bones.get(bone.name)
        rows.append({
            "bone": bone.name,
            "matrix_basis": [list(row) for row in bone.matrix_basis],
            "matrix": [
                list(row)
                for row in (evaluated_bone.matrix if evaluated_bone is not None else bone.matrix)
            ],
        })
    return json.dumps(rows, ensure_ascii=False, separators=(",", ":"))


def _apply_continuity_pose(scene, settings, action) -> int:
    if settings.start_behavior != "CURRENT_POSE":
        return 0
    if action is None:
        raise RuntimeError("Motion Bridge 未返回可写入衔接姿态的角色 Action")
    target = settings.target_rig
    if target is None or target.type != "ARMATURE":
        raise RuntimeError("衔接姿态写入时找不到目标角色骨架")
    try:
        rows = json.loads(settings.continuity_pose_json)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("当前姿态快照无效，无法衔接上一段动作") from exc
    animation_data = target.animation_data_create()
    if animation_data.action != action:
        animation_data.action = action
    frame = int(settings.motion_start_frame)
    channels_by_bone = _action_bone_channels(action)
    if not channels_by_bone:
        raise RuntimeError("角色 Action 没有可用于首帧衔接的骨骼变换通道")
    rows_by_name = {
        row.get("bone", ""): row
        for row in rows
        if isinstance(row, dict) and row.get("bone")
    }
    ordered_bones = sorted(
        (bone for bone in target.pose.bones if bone.name in rows_by_name),
        key=lambda bone: len(bone.parent_recursive),
    )
    animated_bones = [
        bone for bone in ordered_bones if channels_by_bone.get(bone.name)
    ]
    if not animated_bones:
        raise RuntimeError("当前姿态快照与新 Action 没有共同的骨骼通道")

    bounds = _action_keyframe_bounds(action)
    if bounds is None:
        raise RuntimeError("角色 Action 没有可用于姿态衔接的关键帧")
    sample_start = frame
    sample_end = max(sample_start, int(math.ceil(bounds[1])))
    animation_data_use_nla = bool(animation_data.use_nla)
    generated_basis: dict[int, dict[str, Matrix]] = {}
    try:
        # Previous clips must not take part in the rebase. Their evaluated pose
        # has already been captured, and mixing their held channels into the new
        # Action is what caused later clips to turn back toward the source rig.
        animation_data.use_nla = False
        for sample_frame in range(sample_start, sample_end + 1):
            scene.frame_set(sample_frame)
            bpy.context.view_layer.update()
            generated_basis[sample_frame] = {
                bone.name: bone.matrix_basis.copy() for bone in animated_bones
            }

        root_motion_names = {
            bone.name
            for bone in animated_bones
            if "location" in channels_by_bone[bone.name]
        }
        root_motion_anchor_names = {
            bone.name
            for bone in animated_bones
            if bone.name in root_motion_names
            and (bone.parent is None or bone.parent.name not in root_motion_names)
        }
        captured_basis = {}
        for bone in animated_bones:
            values = rows_by_name[bone.name].get("matrix_basis")
            if isinstance(values, list) and len(values) == 4:
                captured_basis[bone.name] = Matrix(values)
        animated_bones = [
            bone for bone in animated_bones if bone.name in captured_basis
        ]
        if not animated_bones:
            raise RuntimeError("当前姿态快照没有可用于安全衔接的局部骨骼变换")

        # Root placement must use the final visible pose (including target
        # constraints), but the visible matrix may be solved only on the top of
        # each Action-owned location chain. Solving both an MMD Center parent
        # and its Groove child bakes the parent's contribution into the child's
        # local location a second time, causing a small positional pop at every
        # Clip seam. Descendant root-motion bones keep their captured local
        # basis. Body/helper bones are never touched during this solve.
        scene.frame_set(sample_start)
        bpy.context.view_layer.update()
        for bone in animated_bones:
            if bone.name not in root_motion_anchor_names:
                continue
            matrix_values = rows_by_name[bone.name].get("matrix")
            if isinstance(matrix_values, list) and len(matrix_values) == 4:
                bone.matrix = Matrix(matrix_values)
        bpy.context.view_layer.update()
        for bone in animated_bones:
            if bone.name in root_motion_anchor_names:
                captured_basis[bone.name] = bone.matrix_basis.copy()

        generated_start = generated_basis[sample_start]
        root_offsets = {}
        for bone in animated_bones:
            if bone.name not in root_motion_names:
                continue
            rest = bone.bone.matrix_local
            if bone.parent is not None:
                rest = bone.parent.matrix @ bone.parent.bone.matrix_local.inverted_safe() @ rest
            up = ((target.matrix_world @ rest).to_3x3().inverted_safe() @ Vector((0, 0, 1))).normalized()
            start_location, start_rotation, _ = generated_start[bone.name].decompose()
            location, rotation, scale = captured_basis[bone.name].decompose()
            full = rotation @ start_rotation.inverted()
            # Only rotation around world vertical is placement. Keeping the
            # entire root delta permanently carries the previous take's lean.
            projection = up * Vector((full.x, full.y, full.z)).dot(up)
            yaw = Quaternion((full.w, *projection))
            if yaw.magnitude < 1e-8:
                yaw = Quaternion()
            else:
                yaw.normalize()
            root_offsets[bone.name] = (start_location, location, scale, full, yaw)
        # Body pose differences are blended out over roughly a quarter second.
        # Applying each limb's start-pose delta to the entire Clip compounds
        # across MMD twist/helper parents and can severely deform the mesh.
        body_blend_frames = min(
            sample_end - sample_start,
            max(2, int(round(scene.render.fps * 0.25))),
        )
        previous_quaternions = {}
        previous_eulers = {}
        for sample_frame in range(sample_start, sample_end + 1):
            scene.frame_set(sample_frame)
            for bone in animated_bones:
                channels = channels_by_bone[bone.name]
                if bone.name in root_motion_names:
                    start_location, location, scale, full, yaw = root_offsets[bone.name]
                    raw_location, raw_rotation, raw_scale = generated_basis[sample_frame][bone.name].decompose()
                    factor = min(1.0, (sample_frame - sample_start) / max(1, body_blend_frames))
                    factor = factor * factor * (3.0 - 2.0 * factor)
                    bone.matrix_basis = Matrix.LocRotScale(
                        location + yaw @ (raw_location - start_location),
                        full.slerp(yaw, factor) @ raw_rotation,
                        scale.lerp(raw_scale, factor),
                    )
                elif sample_frame <= sample_start + body_blend_frames:
                    factor = (
                        (sample_frame - sample_start) / body_blend_frames
                        if body_blend_frames > 0
                        else 1.0
                    )
                    factor = factor * factor * (3.0 - 2.0 * factor)
                    captured_location, captured_rotation, captured_scale = (
                        captured_basis[bone.name].decompose()
                    )
                    generated_location, generated_rotation, generated_scale = (
                        generated_basis[sample_frame][bone.name].decompose()
                    )
                    bone.matrix_basis = Matrix.LocRotScale(
                        captured_location.lerp(generated_location, factor),
                        captured_rotation.slerp(generated_rotation, factor),
                        captured_scale.lerp(generated_scale, factor),
                    )
                else:
                    continue

                if "rotation_quaternion" in channels:
                    value = bone.rotation_quaternion.copy()
                    previous = previous_quaternions.get(bone.name)
                    if previous is not None and previous.dot(value) < 0.0:
                        value.negate()
                        bone.rotation_quaternion = value
                    previous_quaternions[bone.name] = value
                elif "rotation_euler" in channels:
                    value = bone.rotation_euler.copy()
                    previous = previous_eulers.get(bone.name)
                    if previous is not None:
                        value.make_compatible(previous)
                        bone.rotation_euler = value
                    previous_eulers[bone.name] = value

                for data_path in (
                    "location",
                    "rotation_quaternion",
                    "rotation_euler",
                    "rotation_axis_angle",
                    "scale",
                ):
                    if data_path in channels:
                        bone.keyframe_insert(
                            data_path,
                            frame=sample_frame,
                            group=bone.name,
                        )
            bpy.context.view_layer.update()
        action["baw_continuity_root_bones"] = ",".join(sorted(root_motion_names))
        action["baw_continuity_root_anchors"] = ",".join(sorted(root_motion_anchor_names))
        action["baw_continuity_body_blend_frames"] = int(body_blend_frames)
    finally:
        animation_data.use_nla = animation_data_use_nla
        scene.frame_set(frame)
        bpy.context.view_layer.update()
    return len(animated_bones)


def _action_keyframe_bounds(action) -> tuple[float, float] | None:
    frames = [
        float(point.co[0])
        for curve in _iter_action_fcurves(action)
        for point in curve.keyframe_points
    ]
    return (min(frames), max(frames)) if frames else None


def _restrict_action_to_clip(action, frame_start: int) -> None:
    if action is None or not hasattr(action, "use_frame_range"):
        return
    bounds = _action_keyframe_bounds(action)
    end = float(action.frame_end) if action.use_frame_range else (
        bounds[1] if bounds is not None else float(frame_start)
    )
    action.use_frame_range = True
    action.frame_start = int(frame_start)
    action.frame_end = max(float(frame_start), end)


def _clip_motion_bounds(action) -> tuple[int, int]:
    start = int(round(float(action.get("bam_motion_frame_start", action.frame_range[0]))))
    end = int(round(float(action.get("bam_motion_frame_end", action.frame_range[1]))))
    return start, max(start, end)


def _prompt_key(value: str) -> str:
    return " ".join(str(value or "").casefold().split()).strip(" …")


def _source_prompt_key(action) -> str:
    # Blender appends .001 etc. when accepting another take of the same prompt.
    name = re.sub(r"\.\d{3,}$", "", action.name)
    if name.startswith("Proscenium_Motion:"):
        name = name.split(":", 1)[1]
    return _prompt_key(name)


def _find_linked_source_action(action):
    linked_name = str(action.get("baw_source_action", "") or "")
    linked = bpy.data.actions.get(linked_name) if linked_name else None
    if linked is not None:
        return linked

    start, end = _clip_motion_bounds(action)
    candidates = [
        candidate
        for candidate in bpy.data.actions
        if candidate.name.startswith("Proscenium_Motion:")
        and tuple(int(round(float(value))) for value in candidate.frame_range) == (start, end)
    ]
    if len(candidates) == 1:
        return candidates[0]

    prompt_hint = _prompt_key(str(action.get("baw_prompt", "") or ""))
    if prompt_hint:
        matching = [
            candidate
            for candidate in candidates
            if prompt_hint.startswith(_source_prompt_key(candidate))
            or _source_prompt_key(candidate).startswith(prompt_hint)
        ]
        if len(matching) == 1:
            return matching[0]
    return None


def _find_linked_prompt_text(settings, action, source_action):
    linked_name = str(action.get("baw_prompt_text", "") or "")
    linked = bpy.data.texts.get(linked_name) if linked_name else None
    source_key = _source_prompt_key(source_action) if source_action is not None else ""
    if linked is not None:
        linked_key = _prompt_key(linked.as_string())
        verified = int(action.get("baw_clip_link_version", 0)) >= 4 and _action_matches_text(action, linked)
        if verified or not source_key or (
            linked_key.startswith(source_key) or source_key.startswith(linked_key)
        ):
            return linked
    candidates = []
    for text in bpy.data.texts:
        content_key = _prompt_key(text.as_string())
        if not content_key or text.get(ROLE_KEY) == PLAN_TEXT_ROLE:
            continue
        score = 0
        if source_key and (
            content_key.startswith(source_key) or source_key.startswith(content_key)
        ):
            score += 100
        if score and text == getattr(settings, "prompt_text", None):
            score += 10
        if score:
            candidates.append((score, text.name, text))
    if not candidates:
        return None
    candidates.sort(key=lambda row: (-row[0], row[1]))
    if len(candidates) > 1 and candidates[0][0] == candidates[1][0]:
        return None
    return candidates[0][2]


def _prompt_keys_match(left: str, right: str) -> bool:
    left_key = _prompt_key(left)
    right_key = _prompt_key(right)
    return bool(
        left_key
        and right_key
        and (left_key.startswith(right_key) or right_key.startswith(left_key))
    )


def _ensure_text_clip_id(text) -> str:
    clip_id = str(text.get("baw_clip_id", "") or "")
    duplicates = [item for item in bpy.data.texts if item != text and item.get("baw_clip_id") == clip_id] if clip_id else []
    if duplicates:
        owner_names = {str(action.get("baw_prompt_text", "")) for action in bpy.data.actions
                       if action.get("baw_clip_id") == clip_id and int(action.get("baw_clip_link_version", 0)) >= 4}
        keeper = next((item for item in [text, *duplicates] if item.name in owner_names), None)
        keeper = keeper or min([text, *duplicates], key=lambda item: item.name)
        if text != keeper:
            clip_id = ""
    if not clip_id:
        clip_id = uuid.uuid4().hex
        text["baw_clip_id"] = clip_id
    return clip_id


def _text_action_links(text) -> dict[str, str]:
    raw = str(text.get("baw_action_links_json", "") or "")
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(value, dict):
        return {}
    return {
        str(target): str(action)
        for target, action in value.items()
        if str(target) and str(action)
    }


def _write_text_action_links(text, links: dict[str, str]) -> None:
    text["baw_action_links_json"] = json.dumps(
        dict(sorted(links.items())),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _action_matches_text(action, text) -> bool:
    if action is None or text is None:
        return False
    if int(action.get("baw_clip_link_version", 0)) >= 4:
        clip_id = str(text.get("baw_clip_id", "") or "")
        if any(item != text and item.get("baw_clip_id") == clip_id for item in bpy.data.texts):
            return bool(clip_id and action.get("baw_clip_id") == clip_id and action.get("baw_prompt_text") == text.name)
        return bool(clip_id and str(action.get("baw_clip_id", "") or "") == clip_id)
    source_action = action if _is_proscenium_source_action(action) else _find_linked_source_action(action)
    if source_action is not None:
        return _prompt_keys_match(
            text.as_string(),
            _source_prompt_key(source_action),
        )
    clip_id = str(text.get("baw_clip_id", "") or "")
    if clip_id and str(action.get("baw_clip_id", "") or "") == clip_id:
        return True
    return _prompt_keys_match(text.as_string(), str(action.get("baw_prompt", "") or ""))


def _replace_action_references(old_action, new_action, target_name: str) -> int:
    if old_action is None or new_action is None or old_action == new_action:
        return 0
    changed = 0
    target = bpy.data.objects.get(target_name) if target_name else None
    animation_data = getattr(target, "animation_data", None) if target is not None else None
    if animation_data is not None:
        if animation_data.action == old_action:
            animation_data.action = new_action
            changed += 1
        for track in animation_data.nla_tracks:
            for strip in track.strips:
                if strip.action == old_action:
                    strip.action = new_action
                    changed += 1
    old_action["baw_replaced_by"] = new_action.name
    old_action.use_fake_user = False
    if old_action.users == 0:
        bpy.data.actions.remove(old_action)
    return changed


def _retire_superseded_sources(text, source_action) -> None:
    if text is None or source_action is None:
        return
    clip_id = str(text.get("baw_clip_id", "") or "")
    for candidate in tuple(bpy.data.actions):
        if candidate == source_action or not _is_proscenium_source_action(candidate):
            continue
        if not _action_matches_text(candidate, text):
            continue
        still_used = any(
            _is_retarget_output_action(output)
            and str(output.get("baw_source_action", "") or "") == candidate.name
            for output in bpy.data.actions
        )
        if still_used:
            continue
        candidate["baw_replaced_by"] = source_action.name
        candidate.use_fake_user = False
        if candidate.users == 0:
            bpy.data.actions.remove(candidate)


def _persist_text_action_link(
    text,
    action,
    source_action=None,
    *,
    replace: bool = False,
) -> None:
    if text is None or action is None:
        return
    clip_id = _ensure_text_clip_id(text)
    content = text.as_string()
    text.use_fake_user = True
    action.use_fake_user = True
    action["baw_clip_id"] = clip_id
    action["baw_prompt_text"] = text.name
    action["baw_prompt"] = content
    action["baw_clip_link_version"] = TEXT_ACTION_LINK_VERSION
    if source_action is not None:
        source_action.use_fake_user = True
        source_action["baw_clip_id"] = clip_id
        source_action["baw_prompt_text"] = text.name
        source_action["baw_prompt"] = content
        source_action["baw_clip_link_version"] = TEXT_ACTION_LINK_VERSION
        text["baw_source_action"] = source_action.name
        action["baw_source_action"] = source_action.name

    text["baw_link_version"] = TEXT_ACTION_LINK_VERSION
    text["baw_current_action"] = action.name
    if _is_proscenium_source_action(action):
        text["baw_source_action"] = action.name
        return

    target_name = _action_target_name(action)
    if not target_name:
        return
    links = _text_action_links(text)
    old_actions = []
    linked_name = links.get(target_name, "")
    linked = bpy.data.actions.get(linked_name) if linked_name else None
    if (
        replace
        and linked is not None
        and linked != action
        and _is_retarget_output_action(linked)
        and _action_target_name(linked) == target_name
        and _action_matches_text(linked, text)
    ):
        old_actions.append(linked)
    if replace:
        old_actions.extend(
            candidate
            for candidate in bpy.data.actions
            if candidate != action
            and _is_retarget_output_action(candidate)
            and _action_target_name(candidate) == target_name
            and _action_matches_text(candidate, text)
        )
    links[target_name] = action.name
    _write_text_action_links(text, links)
    text["baw_target_object"] = target_name
    for old_action in dict.fromkeys(old_actions):
        _replace_action_references(old_action, action, target_name)
    if replace:
        _retire_superseded_sources(text, source_action)


def _resolve_text_action(scene, settings, text, *, target=None, persist: bool = False):
    if text is None or not _prompt_key(text.as_string()):
        return None
    target_name = target.name if target is not None else ""
    links = _text_action_links(text)
    preferred_names = []
    if target_name and links.get(target_name):
        preferred_names.append(links[target_name])
    current_name = str(text.get("baw_current_action", "") or "")
    source_name = str(text.get("baw_source_action", "") or "")
    preferred_names.extend(name for name in (current_name, source_name) if name)
    for name in dict.fromkeys(preferred_names):
        candidate = bpy.data.actions.get(name)
        if candidate is not None and (
            _is_retarget_output_action(candidate) or _is_proscenium_source_action(candidate)
        ) and _action_matches_text(candidate, text):
            source_action = (
                candidate
                if _is_proscenium_source_action(candidate)
                else _find_linked_source_action(candidate)
            )
            if persist:
                _persist_text_action_link(text, candidate, source_action, replace=False)
            return candidate

    clip_id = str(text.get("baw_clip_id", "") or "")
    ranked = []
    for candidate in bpy.data.actions:
        if not (_is_retarget_output_action(candidate) or _is_proscenium_source_action(candidate)):
            continue
        if not _action_matches_text(candidate, text):
            continue
        owner = _action_target_name(candidate)
        score = 0
        if clip_id and str(candidate.get("baw_clip_id", "") or "") == clip_id:
            score += 1000
        if target_name and owner == target_name:
            score += 400
        elif not owner:
            score += 180
        elif target_name:
            score += 80
        if _is_retarget_output_action(candidate):
            score += 40
        linked_text = str(candidate.get("baw_prompt_text", "") or "")
        if linked_text == text.name:
            score += 20
        ranked.append((score, candidate.name, candidate))
    if not ranked:
        return None
    ranked.sort(key=lambda row: (-row[0], row[1]))
    candidate = ranked[0][2]
    source_action = candidate if _is_proscenium_source_action(candidate) else _find_linked_source_action(candidate)
    if persist:
        _persist_text_action_link(text, candidate, source_action, replace=False)
    return candidate


def _repair_owned_nla_clip_references(scene) -> int:
    """Repair only BA-owned strips whose referenced Action has a different Clip range."""
    repaired = 0
    for target in scene.objects:
        if target.type != "ARMATURE":
            continue
        animation_data = getattr(target, "animation_data", None)
        if animation_data is None:
            continue
        for track in animation_data.nla_tracks:
            if not track.name.startswith("BAW_上一段_"):
                continue
            for strip in track.strips:
                current = strip.action
                if current is None:
                    continue
                expected = (
                    int(round(float(strip.action_frame_start))),
                    int(round(float(strip.action_frame_end))),
                )
                if _clip_motion_bounds(current) == expected:
                    continue
                candidates = []
                for action in bpy.data.actions:
                    if (
                        not _is_retarget_output_action(action)
                        or _action_target_name(action) != target.name
                        or _clip_motion_bounds(action) != expected
                    ):
                        continue
                    text_name = str(action.get("baw_prompt_text", "") or "")
                    prompt_text = bpy.data.texts.get(text_name) if text_name else None
                    if prompt_text is None or not _action_matches_text(action, prompt_text):
                        continue
                    score = 100
                    if str(prompt_text.get("baw_current_action", "") or "") == action.name:
                        score += 50
                    if _text_action_links(prompt_text).get(target.name) == action.name:
                        score += 25
                    candidates.append((score, action.name, action))
                if not candidates:
                    continue
                candidates.sort(key=lambda row: (-row[0], row[1]))
                if len(candidates) > 1 and candidates[0][0] == candidates[1][0]:
                    continue
                strip.action = candidates[0][2]
                repaired += 1
    if repaired:
        settings = getattr(scene, "baw_auto_director", None)
        if settings is not None:
            settings.status_level = "READY"
            settings.status_message = f"已自动恢复 {repaired} 个被错误替换的上一段动作条带"
    return repaired


def _resolve_action_link(scene, settings, action, *, persist: bool = False):
    if _is_proscenium_source_action(action):
        prompt_text = _find_linked_prompt_text(settings, action, action)
        if persist:
            action.use_fake_user = True
            if prompt_text is not None:
                _persist_text_action_link(prompt_text, action, action, replace=False)
        return action, prompt_text
    if not _is_retarget_output_action(action):
        raise RuntimeError("所选 Action 不是 Motion Bridge 生成的角色动作")
    source_action = _find_linked_source_action(action)
    prompt_text = _find_linked_prompt_text(settings, action, source_action)
    if persist:
        start, end = _clip_motion_bounds(action)
        action["baw_clip_link_version"] = 1
        action["baw_clip_start"] = start
        action["baw_clip_end"] = end
        if source_action is not None:
            source_action.use_fake_user = True
            action["baw_source_action"] = source_action.name
        if prompt_text is not None:
            _persist_text_action_link(
                prompt_text,
                action,
                source_action,
                replace=False,
            )
    return source_action, prompt_text


def _associate_generated_action(scene, settings, action, prompt_text=None):
    if action is None:
        return None, None
    source_action = _find_linked_source_action(action)
    if source_action is None:
        bridge = getattr(scene, "ba_motion_bridge_settings", None)
        source = getattr(bridge, "source_rig", None) if bridge is not None else None
        animation_data = getattr(source, "animation_data", None)
        source_actions = []
        if animation_data is not None and animation_data.action is not None:
            source_actions.append(animation_data.action)
        if animation_data is not None:
            source_actions.extend(
                strip.action
                for track in animation_data.nla_tracks
                if not track.mute
                for strip in track.strips
                if strip.action is not None and not strip.mute
            )
        start, end = _clip_motion_bounds(action)
        matching = [
            candidate
            for candidate in dict.fromkeys(source_actions)
            if tuple(int(round(float(value))) for value in candidate.frame_range) == (start, end)
        ]
        if len(matching) == 1:
            source_action = matching[0]
    prompt_text = prompt_text or getattr(settings, "prompt_text", None)
    if prompt_text is None:
        prompt_text = _find_linked_prompt_text(settings, action, source_action)
    if source_action is not None:
        action["baw_source_action"] = source_action.name
    if prompt_text is not None:
        action["baw_prompt_text"] = prompt_text.name
        action["baw_prompt"] = prompt_text.as_string()
        _persist_text_action_link(
            prompt_text,
            action,
            source_action,
            replace=True,
        )
    return source_action, prompt_text


def _find_previous_target_action(target, selected_action, clip_start: int):
    animation_data = getattr(target, "animation_data", None)
    if animation_data is None:
        return None
    candidates = []
    active = animation_data.action
    if active is not None and active != selected_action:
        _active_start, active_end = _clip_motion_bounds(active)
        if active_end == clip_start:
            candidates.append((float(_active_start), active))
    for track in animation_data.nla_tracks:
        for strip in track.strips:
            action = strip.action
            if action is None or action == selected_action:
                continue
            if abs(float(strip.frame_end) - clip_start) < 1e-4:
                candidates.append((float(strip.frame_start), action))
    if candidates:
        candidates.sort(key=lambda row: row[0], reverse=True)
        return candidates[0][1]
    return None


def _unique_action_name(base: str) -> str:
    if bpy.data.actions.get(base) is None:
        return base
    index = 2
    while bpy.data.actions.get(f"{base}.{index:03d}") is not None:
        index += 1
    return f"{base}.{index:03d}"


def _action_target_name(action) -> str:
    return str(action.get("bam_target_object", "") or "") if action is not None else ""


def _requested_reuse_action(settings, action_name: str = ""):
    """Resolve from the selected Text first; the button's Action name is only fallback."""
    selected = bpy.data.actions.get(str(action_name or "")) if action_name else None
    prompt_text = getattr(settings, "remap_prompt_text", None)
    if prompt_text is not None:
        scene = getattr(settings, "id_data", None)
        resolved = _resolve_text_action(
            scene,
            settings,
            prompt_text,
            target=getattr(settings, "reuse_target_rig", None),
            persist=True,
        )
        if resolved is None:
            raise RuntimeError(f"文本块 {prompt_text.name} 找不到可复用动作")
        selected = resolved
    elif selected is None:
        selected = getattr(settings, "remap_action", None)
    if selected is None:
        raise RuntimeError("请选择要导入的来源动作")
    if not (_is_retarget_output_action(selected) or _is_orphan_source_action(selected)):
        raise RuntimeError(f"{selected.name} 不是可复用动作，也不是待恢复的 Proscenium 源动作")
    return selected


def _reusable_actions_for_owner(selected_action) -> list:
    owner = _action_target_name(selected_action)
    if not owner:
        return [selected_action]
    by_bounds = {}
    for action in bpy.data.actions:
        if (
            action.get("bam_role") != "RETARGET_OUTPUT"
            or action.get("baw_replaced_by")
            or _action_target_name(action) != owner
        ):
            continue
        bounds = _clip_motion_bounds(action)
        incumbent = by_bounds.get(bounds)
        if incumbent is None or action == selected_action:
            by_bounds[bounds] = action
    return sorted(by_bounds.values(), key=lambda action: (*_clip_motion_bounds(action), action.name))


def _target_has_reusable_motion(target) -> bool:
    animation_data = getattr(target, "animation_data", None)
    if animation_data is None:
        return False
    if animation_data.action is not None:
        return True
    return any(strip.action is not None for track in animation_data.nla_tracks for strip in track.strips)


def _import_linked_action(context, settings, selected, target, previous=None):
    """Retarget one accepted source Action to another rig without touching the old rig."""
    scene = context.scene
    bridge = getattr(scene, "ba_motion_bridge_settings", None)
    if bridge is None:
        raise RuntimeError("Proscenium Motion Bridge 场景设置尚未注册")
    source_action, prompt_text = _resolve_action_link(scene, settings, selected, persist=True)
    if source_action is None:
        raise RuntimeError(f"{selected.name} 找不到已接受的 Proscenium 源 Action")
    source = bpy.data.objects.get(str(selected.get("bam_source_object", "") or ""))
    if source is None:
        source = bridge.source_rig
    if source is None or source.type != "ARMATURE" or source == target:
        raise RuntimeError(f"{selected.name} 关联的 Proscenium 源骨架已不存在")

    start, _end = _clip_motion_bounds(selected)
    preroll_start = int(round(float(selected.get("bam_preroll_frame_start", start))))
    target_animation = target.animation_data_create()
    source_animation = source.animation_data_create()
    target_action_before = target_animation.action
    target_use_nla_before = bool(target_animation.use_nla)
    source_action_before = source_animation.action
    source_use_nla_before = bool(source_animation.use_nla)
    frame_before = int(scene.frame_current)
    settings_fields = (
        "target_rig",
        "start_behavior",
        "motion_start_frame",
        "preroll_start_frame",
        "continuity_pose_json",
        "previous_clip_action",
        "previous_clip_action_name",
        "previous_clip_use_nla",
    )
    settings_before = {name: getattr(settings, name) for name in settings_fields}
    bridge_fields = (
        "source_rig",
        "target_rig",
        "root_motion_policy",
        "follow_proscenium_inplace",
        "use_start_buffer",
        "initial_pose_source",
        "initial_pose_action",
        "initial_pose_frame",
        "settle_frames",
        "transition_frames",
        "evaluate_physics_preroll",
        "motion_space",
        "use_end_effector_guard",
        "end_effector_guard_strength",
        "constraint_snapshot_json",
        "constraint_snapshot_target",
        "constraint_snapshot_target_rig",
        "previous_target_state_available",
        "previous_target_rig",
        "previous_target_action",
        "previous_target_action_name",
        "previous_target_action_slot",
        "previous_target_use_nla",
        "previous_target_action_fake_user",
        "target_switch_snapshot_json",
        "target_switch_snapshot_target",
        "physics_cache_snapshot_json",
        "timeline_snapshot_json",
    )
    bridge_before = {name: getattr(bridge, name) for name in bridge_fields}
    tracks_before = {track.as_pointer() for track in target_animation.nla_tracks}
    new_action = None
    success = False
    seam_pair = None
    try:
        from .split_seam import Transaction
        seam_pair = Transaction(previous, selected, target)
        settings.target_rig = target
        continuity_json = ""
        if previous is not None:
            target_animation.action = previous
            target_animation.use_nla = False
            scene.frame_set(start)
            bpy.context.view_layer.update()
            continuity_json = _capture_current_pose(target)
        else:
            target_animation.action = target_action_before
            target_animation.use_nla = target_use_nla_before
            scene.frame_set(start)
            bpy.context.view_layer.update()

        bridge.source_rig = source
        bridge.target_rig = target
        if bridge.previous_target_state_available:
            try:
                recovery_target = bridge.previous_target_rig
            except ReferenceError:
                recovery_target = None
            if recovery_target is not None and recovery_target.name != target.name:
                switch_result = bpy.ops.ba_motion_bridge.resolve_target_switch(
                    "EXEC_DEFAULT",
                    mode="KEEP",
                )
                if switch_result != {"FINISHED"}:
                    raise RuntimeError(f"Motion Bridge 无法安全切换到新模型：{switch_result}")
        bridge.root_motion_policy = "FULL"
        bridge.follow_proscenium_inplace = False
        bridge.motion_space = str(selected.get("bam_motion_space", bridge.motion_space))
        bridge.use_end_effector_guard = bool(
            selected.get("bam_end_effector_guard", bridge.use_end_effector_guard)
        )
        bridge.end_effector_guard_strength = float(
            selected.get(
                "bam_end_effector_guard_strength",
                bridge.end_effector_guard_strength,
            )
        )
        bridge.use_start_buffer = previous is None and preroll_start < start
        if bridge.use_start_buffer:
            # A broken old target Action must never seed the new model. Start from
            # the new rig's own current/rest pose and reuse only the accepted source.
            bridge.initial_pose_source = "CURRENT"
            bridge.initial_pose_action = None
            bridge.initial_pose_frame = start
            bridge.settle_frames = 0
            bridge.transition_frames = start - preroll_start
            bridge.evaluate_physics_preroll = bool(
                selected.get("bam_physics_preroll_status", "") == "EVALUATED"
            )

        source_animation.action = source_action
        source_animation.use_nla = False
        scene.frame_set(start)
        bpy.context.view_layer.update()
        result = bpy.ops.ba_motion_bridge.retarget("EXEC_DEFAULT")
        if result != {"FINISHED"}:
            raise RuntimeError(f"Motion Bridge 重新映射未完成：{result}")
        new_action = bpy.data.actions.get(bridge.last_output_action)
        if new_action is None or new_action == selected:
            raise RuntimeError("Motion Bridge 没有返回新的独立 Action")
        if bridge.use_start_buffer and preroll_start < start:
            new_action.use_frame_range = True
            new_action.frame_start = preroll_start
            new_action.frame_end = max(float(start), float(new_action.frame_end))

        foot_raw = None
        if settings.reuse_foot_contact:
            from . import foot_contact
            foot_raw = foot_contact.capture_root(scene, source, target, new_action, start, _end)
        if previous is not None:
            settings.start_behavior = "CURRENT_POSE"
            settings.motion_start_frame = start
            settings.preroll_start_frame = start
            settings.continuity_pose_json = continuity_json
            settings.previous_clip_action = previous
            settings.previous_clip_action_name = previous.name
            settings.previous_clip_use_nla = target_use_nla_before
            _apply_continuity_pose(scene, settings, new_action)
            _preserve_previous_clip(settings, new_action)
        else:
            target_animation.action = new_action
            target_animation.action_blend_type = "REPLACE"
            target_animation.action_extrapolation = "NOTHING"
            target_animation.action_influence = 1.0
            target_animation.use_nla = target_use_nla_before

        if foot_raw is not None:
            foot_contact.apply(scene, source, target, new_action, start, _end, foot_raw)
        if settings.reuse_seam_smoothing:
            if settings.reuse_seam_mode == 'SPLIT':
                seam_pair.apply(scene,target,new_action,start,_end,settings.reuse_seam_frames)
            else:
                from . import seam_smoothing
                seam_smoothing.apply(scene,target,new_action,previous,start,_end,settings.reuse_seam_frames)
        source_action.use_fake_user = True
        new_action["baw_source_action"] = source_action.name
        new_action["baw_reused_from_action"] = selected.name
        new_action["baw_reused_from_target"] = _action_target_name(selected)
        new_action["baw_clip_link_version"] = 2
        new_action["baw_clip_start"] = start
        new_action["baw_clip_end"] = _clip_motion_bounds(selected)[1]
        if prompt_text is not None:
            prompt_text.use_fake_user = True
            new_action["baw_prompt_text"] = prompt_text.name
            new_action["baw_prompt"] = prompt_text.as_string()
            _persist_text_action_link(
                prompt_text,
                new_action,
                source_action,
                replace=True,
            )
        seam_pair.commit()
        success = True
        return new_action, prompt_text
    finally:
        source_animation.action = source_action_before
        source_animation.use_nla = source_use_nla_before
        for name, value in bridge_before.items():
            if getattr(bridge, name) != value:
                setattr(bridge, name, value)
        for name, value in settings_before.items():
            try:
                setattr(settings, name, value)
            except ReferenceError:
                setattr(settings, name, None if name == "previous_clip_action" else "")
        if not success:
            if seam_pair is not None:
                seam_pair.rollback()
            for track in tuple(target_animation.nla_tracks):
                if track.as_pointer() not in tracks_before:
                    target_animation.nla_tracks.remove(track)
            target_animation.action = target_action_before
            target_animation.use_nla = target_use_nla_before
            if new_action is not None and new_action != selected:
                new_action.use_fake_user = False
                if new_action.users == 0:
                    bpy.data.actions.remove(new_action)
        scene.frame_set(frame_before)
        bpy.context.view_layer.update()


def _preserve_previous_clip(settings, new_action) -> int:
    if settings.start_behavior != "CURRENT_POSE":
        return 0
    target = settings.target_rig
    if target is None or target.type != "ARMATURE":
        raise RuntimeError("保留上一段动作时找不到目标角色骨架")
    animation_data = target.animation_data_create()
    try:
        previous = settings.previous_clip_action
    except ReferenceError:
        previous = None
    if previous is None and settings.previous_clip_action_name:
        previous = bpy.data.actions.get(settings.previous_clip_action_name)

    animation_data.use_nla = bool(settings.previous_clip_use_nla or previous is not None)
    if new_action is not None:
        _restrict_action_to_clip(new_action, int(settings.motion_start_frame))
        animation_data.action = new_action
        animation_data.action_blend_type = "REPLACE"
        animation_data.action_extrapolation = "NOTHING"
        animation_data.action_influence = 1.0
    # Upgrade strips created by 0.5.8 and earlier. Only BA-owned continuity
    # tracks are touched; user-authored NLA extrapolation remains unchanged.
    for track in animation_data.nla_tracks:
        if track.name.startswith("BAW_上一段_"):
            for strip in track.strips:
                strip.extrapolation = "NOTHING"
    if previous is None or previous == new_action:
        return 0

    previous.use_fake_user = True
    if any(
        getattr(strip, "action", None) == previous
        for track in animation_data.nla_tracks
        for strip in track.strips
    ):
        return 0

    action_start, action_end = (float(value) for value in previous.frame_range)
    playback_start = float(previous.get("bam_preroll_frame_start", action_start))
    bounds = _action_keyframe_bounds(previous)
    if bounds is not None:
        playback_start = max(bounds[0], min(playback_start, action_start))
        action_end = max(action_end, bounds[1])
    if hasattr(previous, "use_frame_range") and playback_start < action_start:
        previous.use_frame_range = True
        previous.frame_start = playback_start
    cutoff = min(action_end, float(settings.motion_start_frame))
    if cutoff <= playback_start:
        return 0
    track = animation_data.nla_tracks.new()
    track.name = f"BAW_上一段_{previous.name}"
    strip = track.strips.new(previous.name, int(math.floor(playback_start)), previous)
    strip.action_frame_start = playback_start
    strip.action_frame_end = cutoff
    strip.frame_start = playback_start
    strip.frame_end = cutoff
    strip.blend_type = "REPLACE"
    # The new active Action owns the pose from the boundary onward. Holding an
    # older REPLACE strip beyond that point leaks channels absent from the new
    # clip and creates a hybrid, twisted pose.
    strip.extrapolation = "NOTHING"
    strip.influence = 1.0
    return 1


def _prepare_start_behavior(context, settings, plan: dict) -> None:
    scene = context.scene
    target = settings.target_rig or find_armature(context)
    if target is None or target.type != "ARMATURE":
        raise RuntimeError("请选择用户模型中的角色骨架")
    settings.target_rig = target
    snapshot = _timeline_snapshot(scene)
    settings.timeline_before_json = json.dumps(snapshot, separators=(",", ":"))
    behavior = _choose_start_behavior(
        _target_has_motion(target),
        snapshot["frame_current"],
        snapshot["frame_start"],
        settings.preroll_margin,
    )
    settings.start_behavior = behavior["mode"]
    settings.motion_start_frame = behavior["motion_start"]
    settings.preroll_start_frame = behavior["preroll_start"]
    bridge = getattr(scene, "ba_motion_bridge_settings", None)
    if bridge is None:
        raise RuntimeError("Motion Bridge 场景设置尚未注册")
    switched_from = _resolve_auto_target_switch(context, bridge, target)
    transition_frames = 0
    if behavior["mode"] == "PREROLL":
        transition_frames = max(0, int(settings.preroll_margin))
        settings.continuity_pose_json = ""
        settings.previous_clip_action = None
        settings.previous_clip_action_name = ""
        settings.previous_clip_use_nla = False
        bridge.use_start_buffer = settings.preroll_margin > 0
        bridge.initial_pose_source = "CURRENT"
        bridge.settle_frames = 0
        bridge.transition_frames = transition_frames
        bridge.evaluate_physics_preroll = True
        settings.last_start_summary = (
            f"正式动作从 {behavior['motion_start']} 帧开始；"
            f"从 {behavior['preroll_start']} 帧开始平滑过渡，共 {transition_frames} 帧"
        )
    else:
        settings.continuity_pose_json = _capture_current_pose(target)
        animation_data = target.animation_data
        previous_action = animation_data.action if animation_data is not None else None
        settings.previous_clip_action = previous_action
        settings.previous_clip_action_name = previous_action.name if previous_action else ""
        settings.previous_clip_use_nla = bool(animation_data and animation_data.use_nla)
        bridge.use_start_buffer = False
        settings.last_start_summary = (
            f"正式动作从 {behavior['motion_start']} 帧开始；保留上一段动作并沿用当前姿态"
        )
    if switched_from:
        settings.last_start_summary = (
            f"已保留 {switched_from} 的输出并切换到 {target.name}；"
            + settings.last_start_summary
        )
    plan["start_behavior"] = {
        **behavior,
        "preroll_margin": int(settings.preroll_margin),
        "transition_frames": transition_frames,
    }


def _finish_timeline(scene, settings, plan: dict, *, completed: bool) -> None:
    snapshot = _load_timeline_snapshot(settings)
    if snapshot is None:
        return
    scene.render.fps = int(plan["fps"]) if completed else int(snapshot["fps"])
    scene.render.fps_base = 1.0 if completed else float(snapshot["fps_base"])
    scene.frame_start = int(snapshot["frame_start"])
    scene.frame_end = (
        max(int(snapshot["frame_end"]), int(plan["frame_end"]))
        if completed else int(snapshot["frame_end"])
    )
    if completed and settings.start_behavior == "PREROLL":
        scene.use_preview_range = True
        old_preview_end = (
            int(snapshot["frame_preview_end"])
            if snapshot["use_preview_range"] else int(snapshot["frame_end"])
        )
        scene.frame_preview_start = int(settings.preroll_start_frame)
        scene.frame_preview_end = max(old_preview_end, scene.frame_end)
        scene.frame_set(int(settings.preroll_start_frame))
        return
    scene.use_preview_range = bool(snapshot["use_preview_range"])
    scene.frame_preview_start = int(snapshot["frame_preview_start"])
    scene.frame_preview_end = (
        max(int(snapshot["frame_preview_end"]), int(plan["frame_end"]))
        if completed and snapshot["use_preview_range"]
        else int(snapshot["frame_preview_end"])
    )
    scene.frame_set(
        int(settings.motion_start_frame) if completed else int(snapshot["frame_current"])
    )


class BAW_OT_auto_prompt_new(bpy.types.Operator):
    bl_idname = "baw.auto_prompt_new"
    bl_label = "新建当前 Clip 多行提示词"
    bl_description = "创建可保存换行与缩进的 Blender 文本块，并导入旧的短提示内容"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        text = _new_prompt_text(context.scene.baw_auto_director)
        self.report({"INFO"}, f"已创建多行提示词：{text.name}")
        return {"FINISHED"}


class BAW_OT_auto_prompt_unlink(bpy.types.Operator):
    bl_idname = "baw.auto_prompt_unlink"
    bl_label = "取消使用当前多行提示词"
    bl_description = "解除当前 Clip 与文本块的关联；文本块本身不会被删除"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        context.scene.baw_auto_director.prompt_text = None
        return {"FINISHED"}


class BAW_OT_auto_prompt_edit(bpy.types.Operator):
    bl_idname = "baw.auto_prompt_edit"
    bl_label = "打开多行提示词编辑器"
    bl_description = "在单独区域打开 Blender 文本编辑器，可直接粘贴和编辑保留换行缩进的完整 Clip"

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.screen is not None

    def execute(self, context):
        settings = context.scene.baw_auto_director
        text = settings.prompt_text or _new_prompt_text(settings)
        for area in context.screen.areas:
            if area.type == "TEXT_EDITOR":
                area.spaces.active.text = text
                area.tag_redraw()
                self.report({"INFO"}, "已在现有文本编辑器中打开当前 Clip")
                return {"FINISHED"}

        before = {area.as_pointer() for area in context.screen.areas}
        direction = "VERTICAL" if context.area.width >= context.area.height else "HORIZONTAL"
        try:
            result = bpy.ops.screen.area_split(
                "EXEC_DEFAULT",
                direction=direction,
                factor=0.62,
            )
        except RuntimeError as exc:
            self.report({"ERROR"}, f"无法打开多行编辑器：{exc}")
            return {"CANCELLED"}
        if result != {"FINISHED"}:
            self.report({"ERROR"}, "Blender 未能拆分编辑区域")
            return {"CANCELLED"}
        editor = next(
            (area for area in context.screen.areas if area.as_pointer() not in before),
            None,
        )
        if editor is None:
            self.report({"ERROR"}, "找不到新建的提示词编辑区域")
            return {"CANCELLED"}
        editor.type = "TEXT_EDITOR"
        editor.spaces.active.text = text
        editor.tag_redraw()
        self.report({"INFO"}, "已打开当前 Clip 多行提示词编辑器；内容会随 .blend 自动保存")
        return {"FINISHED"}


class BAW_OT_auto_compile_plan(bpy.types.Operator):
    bl_idname = "baw.auto_compile_plan"
    bl_label = "生成导演方案"
    bl_description = "从当前提示词与总帧数生成一个透明、可检查的单段方案，不调用云端额度"
    bl_options = {"REGISTER"}

    def execute(self, context):
        settings = context.scene.baw_auto_director
        try:
            plan = compile_plan(settings, placement_frame=context.scene.frame_current)
            write_plan(context.scene, settings, plan)
        except ValueError as exc:
            _set_status(settings, "ERROR", str(exc), "ERROR", 0.0)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        _set_status(settings, "PLAN_READY", f"方案已生成：{plan['timing_summary']}", "READY", 0.05)
        self.report({"INFO"}, "导演方案已写入 BAW_自动导演方案 文本块")
        return {"FINISHED"}


class BAW_OT_auto_build_scene(bpy.types.Operator):
    bl_idname = "baw.auto_build_scene"
    bl_label = "仅搭建场景"
    bl_description = "按当前描述生成或刷新插件拥有的实验场景、灯光和镜头，不生成动作"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.baw_auto_director
        try:
            plan = compile_plan(settings, placement_frame=context.scene.frame_current)
            write_plan(context.scene, settings, plan)
            count = build_generated_scene(context, plan)
        except (RuntimeError, ValueError) as exc:
            _set_status(settings, "ERROR", str(exc), "ERROR", 0.0)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        _set_status(settings, "SCENE_READY", f"实验场景已刷新：{count} 个受控对象", "READY", 0.15)
        self.report({"INFO"}, settings.status_message)
        return {"FINISHED"}


class BAW_OT_auto_remap_existing(bpy.types.Operator):
    bl_idname = "baw.auto_remap_existing"
    bl_label = "重新映射并替换所选动作"
    bl_description = (
        "复用所选动作关联的已接受 Proscenium 源 Action，重新映射到当前角色并原位替换；"
        "不调用动作生成服务，旧 Action 会保留为可回退备份"
    )
    bl_options = {"REGISTER", "UNDO"}

    action_name: StringProperty(
        name="来源动作",
        description="点击按钮时锁定的来源 Action",
        default="",
        options={"HIDDEN", "SKIP_SAVE"},
    )

    @classmethod
    def poll(cls, context):
        settings = getattr(context.scene, "baw_auto_director", None)
        return bool(settings and settings.remap_action is not None)

    def execute(self, context):
        scene = context.scene
        settings = scene.baw_auto_director
        bridge = getattr(scene, "ba_motion_bridge_settings", None)
        try:
            selected = _requested_reuse_action(settings, self.action_name)
        except RuntimeError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        target = settings.reuse_target_rig or settings.target_rig
        if bridge is None or target is None or target.type != "ARMATURE":
            self.report({"ERROR"}, "请选择重新映射目标模型，并确认 Proscenium Motion Bridge 已启用")
            return {"CANCELLED"}
        target_animation = target.animation_data_create()
        belongs_to_target = target_animation.action == selected or any(
            strip.action == selected
            for track in target_animation.nla_tracks
            for strip in track.strips
        )
        if not belongs_to_target:
            owner = _action_target_name(selected) or "未知"
            self.report(
                {"ERROR"},
                f"所选动作属于 {owner}，当前目标为 {target.name}；请改用“导入所选动作到新模型”",
            )
            return {"CANCELLED"}
        try:
            source_action, prompt_text = _resolve_action_link(
                scene,
                settings,
                selected,
                persist=True,
            )
        except RuntimeError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        if source_action is None:
            self.report({"ERROR"}, "找不到与所选动作帧范围对应的已接受 Proscenium 源 Action")
            return {"CANCELLED"}
        source = bpy.data.objects.get(str(selected.get("bam_source_object", "") or ""))
        if source is None:
            source = bridge.source_rig
        if source is None or source.type != "ARMATURE" or source == target:
            self.report({"ERROR"}, "所选动作关联的 Proscenium 源骨架已不存在")
            return {"CANCELLED"}

        source_animation = source.animation_data_create()
        active_before = target_animation.action
        target_use_nla_before = bool(target_animation.use_nla)
        source_active_before = source_animation.action
        source_use_nla_before = bool(source_animation.use_nla)
        frame_before = int(scene.frame_current)
        start, _end = _clip_motion_bounds(selected)
        previous = _find_previous_target_action(target, selected, start)
        strip_rows = [
            (
                strip,
                strip.action,
                float(strip.frame_start),
                float(strip.frame_end),
                float(strip.action_frame_start),
                float(strip.action_frame_end),
            )
            for track in target_animation.nla_tracks
            for strip in track.strips
            if strip.action == selected
        ]
        bridge_fields = (
            "source_rig",
            "target_rig",
            "root_motion_policy",
            "follow_proscenium_inplace",
            "use_start_buffer",
            "initial_pose_source",
            "initial_pose_action",
            "initial_pose_frame",
            "settle_frames",
            "transition_frames",
            "evaluate_physics_preroll",
            "motion_space",
            "use_end_effector_guard",
            "end_effector_guard_strength",
            "constraint_snapshot_json",
            "constraint_snapshot_target",
            "constraint_snapshot_target_rig",
            "previous_target_state_available",
            "previous_target_rig",
            "previous_target_action",
            "previous_target_action_name",
            "previous_target_action_slot",
            "previous_target_use_nla",
            "previous_target_action_fake_user",
            "target_switch_snapshot_json",
            "target_switch_snapshot_target",
            "physics_cache_snapshot_json",
            "timeline_snapshot_json",
        )
        bridge_before = {name: getattr(bridge, name) for name in bridge_fields}
        continuity_json = ""
        new_action = None
        seam_pair = None
        try:
            from .split_seam import Transaction
            seam_pair = Transaction(previous, selected, target)
            if previous is not None:
                target_animation.action = previous
                target_animation.use_nla = False
                scene.frame_set(start)
                bpy.context.view_layer.update()
                continuity_json = _capture_current_pose(target)
            target_animation.action = active_before
            target_animation.use_nla = target_use_nla_before

            bridge.source_rig = source
            bridge.target_rig = target
            if bridge.previous_target_state_available:
                try:
                    recovery_target = bridge.previous_target_rig
                except ReferenceError:
                    recovery_target = None
                if recovery_target is not None and recovery_target.name != target.name:
                    switch_result = bpy.ops.ba_motion_bridge.resolve_target_switch(
                        "EXEC_DEFAULT",
                        mode="KEEP",
                    )
                    if switch_result != {"FINISHED"}:
                        raise RuntimeError(f"Motion Bridge 无法安全切换到目标模型：{switch_result}")
            bridge.root_motion_policy = "FULL"
            bridge.follow_proscenium_inplace = False
            bridge.motion_space = str(selected.get("bam_motion_space", bridge.motion_space))
            bridge.use_end_effector_guard = bool(
                selected.get("bam_end_effector_guard", bridge.use_end_effector_guard)
            )
            bridge.end_effector_guard_strength = float(
                selected.get(
                    "bam_end_effector_guard_strength",
                    bridge.end_effector_guard_strength,
                )
            )
            preroll_start = int(round(float(selected.get("bam_preroll_frame_start", start))))
            bridge.use_start_buffer = previous is None and preroll_start < start
            if bridge.use_start_buffer:
                bridge.initial_pose_source = "ACTION_FRAME"
                bridge.initial_pose_action = selected
                bridge.initial_pose_frame = preroll_start
                bridge.settle_frames = int(selected.get("bam_preroll_settle_frames", 0))
                bridge.transition_frames = int(
                    selected.get("bam_preroll_transition_frames", start - preroll_start)
                )
                bridge.evaluate_physics_preroll = bool(
                    selected.get("bam_physics_preroll_status", "") == "EVALUATED"
                )

            source_animation.action = source_action
            source_animation.use_nla = False
            scene.frame_set(start)
            bpy.context.view_layer.update()
            result = bpy.ops.ba_motion_bridge.retarget("EXEC_DEFAULT")
            if result != {"FINISHED"}:
                raise RuntimeError(f"Motion Bridge 重新映射未完成：{result}")
            new_action = bpy.data.actions.get(bridge.last_output_action)
            if new_action is None or new_action == selected:
                raise RuntimeError("Motion Bridge 没有返回新的独立 Action")
            if bridge.use_start_buffer and preroll_start < start:
                new_action.use_frame_range = True
                new_action.frame_start = preroll_start
                new_action.frame_end = max(float(start), float(new_action.frame_end))

            foot_raw = None
            if settings.reuse_foot_contact:
                from . import foot_contact
                foot_raw = foot_contact.capture_root(scene, source, target, new_action, start, _clip_motion_bounds(selected)[1])
            if previous is not None:
                settings.start_behavior = "CURRENT_POSE"
                settings.motion_start_frame = start
                settings.continuity_pose_json = continuity_json
                _apply_continuity_pose(scene, settings, new_action)
            if foot_raw is not None:
                foot_contact.apply(scene, source, target, new_action, start, _clip_motion_bounds(selected)[1], foot_raw)
            if settings.reuse_seam_smoothing:
                if settings.reuse_seam_mode == 'SPLIT':
                    seam_pair.apply(scene,target,new_action,start,_end,settings.reuse_seam_frames)
                else:
                    from . import seam_smoothing
                    seam_smoothing.apply(scene,target,new_action,previous,start,_end,settings.reuse_seam_frames)
            if prompt_text is not None:
                new_action["baw_prompt_text"] = prompt_text.name
                new_action["baw_prompt"] = prompt_text.as_string()
            new_action["baw_source_action"] = source_action.name

            for strip, _old, frame_start, frame_end, action_start, action_end in strip_rows:
                strip.action = new_action
                strip.action_frame_start = action_start
                strip.action_frame_end = action_end
                strip.frame_start = frame_start
                strip.frame_end = frame_end

            if active_before == selected:
                target_animation.action = new_action
            else:
                target_animation.action = active_before
            target_animation.use_nla = target_use_nla_before

            old_name = selected.name
            backup_name = _unique_action_name(f"{old_name}_BAW_替换前")
            selected.name = backup_name
            new_action.name = old_name
            selected["baw_replaced_by"] = new_action.name
            new_action["baw_remapped_from"] = backup_name
            if prompt_text is not None:
                _persist_text_action_link(
                    prompt_text,
                    new_action,
                    source_action,
                    replace=True,
                )
            bridge.last_output_action = new_action.name
            settings.remap_action = new_action
            if prompt_text is not None:
                settings.remap_prompt_text = prompt_text
            seam_pair.commit()
        except Exception as exc:
            if seam_pair is not None:
                seam_pair.rollback()
            for strip, old_action, frame_start, frame_end, action_start, action_end in strip_rows:
                strip.action = old_action
                strip.action_frame_start = action_start
                strip.action_frame_end = action_end
                strip.frame_start = frame_start
                strip.frame_end = frame_end
            target_animation.action = active_before
            target_animation.use_nla = target_use_nla_before
            if new_action is not None and new_action != selected:
                new_action.use_fake_user = False
                if new_action.users == 0:
                    bpy.data.actions.remove(new_action)
            _set_status(settings, "ERROR", f"已有动作重新映射失败：{exc}", "ERROR", settings.progress)
            self.report({"ERROR"}, settings.status_message)
            return {"CANCELLED"}
        finally:
            source_animation.action = source_active_before
            source_animation.use_nla = source_use_nla_before
            for name, value in bridge_before.items():
                if getattr(bridge, name) != value:
                    setattr(bridge, name, value)
            scene.frame_set(frame_before)
            bpy.context.view_layer.update()

        text_note = f"；关联文本 {prompt_text.name}" if prompt_text is not None else ""
        _set_status(
            settings,
            "COMPLETE",
            f"已重新映射并原位替换：{new_action.name}{text_note}；旧动作已保留为 {backup_name}",
            "READY",
            1.0,
        )
        self.report({"INFO"}, settings.status_message)
        return {"FINISHED"}


class BAW_OT_auto_import_existing(bpy.types.Operator):
    bl_idname = "baw.auto_import_existing"
    bl_label = "导入所选动作到新模型"
    bl_description = (
        "从所选旧动作找回已接受的 Proscenium 源 Action，映射到新模型；"
        "不会读取或修改旧模型的骨骼姿态，也不会重新生成动作"
    )
    bl_options = {"REGISTER", "UNDO"}

    action_name: StringProperty(
        name="来源动作",
        description="点击按钮时锁定的来源 Action；不会随时间轴当前片段变化",
        default="",
        options={"HIDDEN", "SKIP_SAVE"},
    )

    @classmethod
    def poll(cls, context):
        settings = getattr(context.scene, "baw_auto_director", None)
        return bool(
            settings
            and settings.remap_action is not None
            and settings.reuse_target_rig is not None
        )

    def execute(self, context):
        settings = context.scene.baw_auto_director
        try:
            selected = _requested_reuse_action(settings, self.action_name)
        except RuntimeError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        target = settings.reuse_target_rig
        if target is None or target.type != "ARMATURE":
            self.report({"ERROR"}, "请选择接收动作的新模型骨架")
            return {"CANCELLED"}
        if _action_target_name(selected) == target.name:
            self.report({"ERROR"}, "来源动作已经属于该模型；请使用“原位重新映射并替换”")
            return {"CANCELLED"}
        start, _end = _clip_motion_bounds(selected)
        previous = _find_previous_target_action(target, None, start)
        if _target_has_reusable_motion(target) and previous is None:
            self.report({"ERROR"}, "新模型已有不衔接此帧段的动作；请选择空白新模型或按顺序导入")
            return {"CANCELLED"}
        try:
            new_action, prompt_text = _import_linked_action(
                context,
                settings,
                selected,
                target,
                previous=previous,
            )
        except Exception as exc:
            _set_status(settings, "ERROR", f"动作复用导入失败：{exc}", "ERROR", settings.progress)
            self.report({"ERROR"}, settings.status_message)
            return {"CANCELLED"}
        text_note = f"；关联文本 {prompt_text.name}" if prompt_text is not None else ""
        _set_status(
            settings,
            "COMPLETE",
            f"已将 {selected.name} 导入到 {target.name}：{new_action.name}{text_note}",
            "READY",
            1.0,
        )
        settings.remap_action = new_action
        if prompt_text is not None:
            settings.remap_prompt_text = prompt_text
        self.report({"INFO"}, settings.status_message)
        return {"FINISHED"}


class BAW_OT_auto_import_all_existing(bpy.types.Operator):
    bl_idname = "baw.auto_import_all_existing"
    bl_label = "按时间轴导入全部关联动作"
    bl_description = (
        "查找与所选动作来自同一旧模型的全部 Clip，按时间顺序映射到空白新模型并重建 NLA 衔接；"
        "全过程不调用动作生成服务"
    )
    bl_options = {"REGISTER", "UNDO"}

    action_name: StringProperty(
        name="来源动作",
        description="点击按钮时锁定的来源 Action，用于识别来源模型的全部 Clip",
        default="",
        options={"HIDDEN", "SKIP_SAVE"},
    )

    @classmethod
    def poll(cls, context):
        settings = getattr(context.scene, "baw_auto_director", None)
        return bool(
            settings
            and settings.remap_action is not None
            and settings.reuse_target_rig is not None
        )

    def execute(self, context):
        scene = context.scene
        settings = scene.baw_auto_director
        try:
            selected = _requested_reuse_action(settings, self.action_name)
        except RuntimeError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        target = settings.reuse_target_rig
        if target is None or target.type != "ARMATURE":
            self.report({"ERROR"}, "请选择接收动作的新模型骨架")
            return {"CANCELLED"}
        owner = _action_target_name(selected)
        if not owner:
            self.report({"ERROR"}, "待恢复的 Proscenium 源动作只能单段导入")
            return {"CANCELLED"}
        if owner == target.name:
            self.report({"ERROR"}, "来源动作已经属于该模型；批量复用需要选择另一个空白新模型")
            return {"CANCELLED"}
        if _target_has_reusable_motion(target):
            self.report({"ERROR"}, "批量导入仅用于空白新模型，以免覆盖现有动作")
            return {"CANCELLED"}
        actions = _reusable_actions_for_owner(selected)
        if not actions:
            self.report({"ERROR"}, "没有找到可复用的动作")
            return {"CANCELLED"}
        try:
            unresolved = [
                action.name
                for action in actions
                if _resolve_action_link(scene, settings, action, persist=True)[0] is None
            ]
        except RuntimeError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        if unresolved:
            self.report({"ERROR"}, f"以下动作缺少已接受源 Action：{', '.join(unresolved)}")
            return {"CANCELLED"}

        animation_data = target.animation_data_create()
        action_before = animation_data.action
        use_nla_before = bool(animation_data.use_nla)
        tracks_before = {track.as_pointer() for track in animation_data.nla_tracks}
        created = []
        batch_id = uuid.uuid4().hex
        previous = None
        try:
            for action in actions:
                new_action, _prompt_text = _import_linked_action(
                    context,
                    settings,
                    action,
                    target,
                    previous=previous,
                )
                new_action["baw_reuse_batch_id"] = batch_id
                created.append(new_action)
                previous = new_action
        except Exception as exc:
            animation_data.action = action_before
            animation_data.use_nla = use_nla_before
            for track in tuple(animation_data.nla_tracks):
                if track.as_pointer() not in tracks_before:
                    animation_data.nla_tracks.remove(track)
            for action in reversed(created):
                action.use_fake_user = False
                if action.users == 0:
                    bpy.data.actions.remove(action)
            _set_status(settings, "ERROR", f"批量动作复用失败，已回滚：{exc}", "ERROR", settings.progress)
            self.report({"ERROR"}, settings.status_message)
            return {"CANCELLED"}

        first_start, _ = _clip_motion_bounds(actions[0])
        _, last_end = _clip_motion_bounds(actions[-1])
        scene.frame_end = max(int(scene.frame_end), last_end)
        _set_status(
            settings,
            "COMPLETE",
            f"已向 {target.name} 导入 {len(created)} 段动作（{first_start}–{last_end} 帧）；旧模型和旧动作未修改",
            "READY",
            1.0,
        )
        self.report({"INFO"}, settings.status_message)
        return {"FINISHED"}


class BAW_OT_auto_finalize_preview(bpy.types.Operator):
    bl_idname = "baw.auto_finalize_preview"
    bl_label = "接受预览并输出到角色"
    bl_description = "明确接受当前 Proscenium 预览，并由 Motion Bridge 生成用户角色的独立动作"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        proscenium = getattr(context.scene, "proscenium", None)
        return bool(proscenium and getattr(proscenium, "is_previewing", False))

    def execute(self, context):
        settings = context.scene.baw_auto_director
        bridge = context.scene.ba_motion_bridge_settings
        try:
            _resolve_auto_target_switch(context, bridge, settings.target_rig)
        except RuntimeError as exc:
            _set_status(settings, "ERROR", f"切换角色失败：{exc}", "ERROR", settings.progress)
            self.report({"ERROR"}, settings.status_message)
            return {"CANCELLED"}
        bridge.accept_preview_on_run = True
        context.scene.frame_set(int(settings.motion_start_frame))
        result = bpy.ops.ba_motion_bridge.accept_and_retarget("EXEC_DEFAULT")
        if result != {"FINISHED"}:
            _set_status(settings, "ERROR", f"角色动作输出未完成：{result}", "ERROR", settings.progress)
            return {"CANCELLED"}
        try:
            plan = json.loads(settings.plan_json) if settings.plan_json else None
            if plan and "fps" in plan and "frame_end" in plan:
                action = bpy.data.actions.get(bridge.last_output_action)
                _preserve_previous_clip(settings, action)
                _apply_continuity_pose(context.scene, settings, action)
                _associate_generated_action(context.scene, settings, action)
                _finish_timeline(context.scene, settings, plan, completed=True)
        except (TypeError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
            _set_status(settings, "ERROR", f"角色动作已输出，但首帧衔接失败：{exc}", "ERROR", settings.progress)
            self.report({"ERROR"}, settings.status_message)
            return {"CANCELLED"}
        summary = settings.last_timing_summary or "动作时间轴"
        _set_status(settings, "COMPLETE", f"当前 Clip 已完成：{summary}；请检查后再输入下一段", "READY", 1.0)
        return {"FINISHED"}


class BAW_OT_auto_cancel(bpy.types.Operator):
    bl_idname = "baw.auto_cancel"
    bl_label = "取消自动生成"
    bl_description = "请求停止当前自动导演任务；服务器端已提交的请求可能仍会完成，但结果会被丢弃"

    def execute(self, context):
        context.scene.baw_auto_director.cancel_requested = True
        self.report({"INFO"}, "已请求取消自动导演任务")
        return {"FINISHED"}


class BAW_OT_auto_clear_scene(bpy.types.Operator):
    bl_idname = "baw.auto_clear_scene"
    bl_label = "清除实验场景"
    bl_description = "仅删除带当前场景所有权标记的自动导演对象，并恢复此前的相机与世界环境"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.baw_auto_director
        count = clear_generated_scene(context.scene, settings, restore_context=True)
        _set_status(settings, "IDLE", f"已清除 {count} 个实验对象；角色与动作未改动", "INFO", 0.0)
        return {"FINISHED"}


class BAW_OT_auto_run(bpy.types.Operator):
    bl_idname = "baw.auto_run"
    bl_label = "运行全自动工作流"
    bl_description = "解析当前 Clip、按需搭建所选场景内容，调用 Proscenium 异步生成动作并输出到用户角色"
    bl_options = {"REGISTER", "UNDO"}

    _timer = None
    _started_at = 0.0
    _plan = None
    _batch_index = 0

    @classmethod
    def poll(cls, context):
        settings = getattr(context.scene, "baw_auto_director", None)
        return bool(settings and settings.state != "RUNNING")

    def invoke(self, context, _event):
        settings = context.scene.baw_auto_director
        self._plan = None
        try:
            plan = compile_plan(settings, placement_frame=context.scene.frame_current)
            write_plan(context.scene, settings, plan)
            _set_status(settings, "RUNNING", "正在准备当前 Clip", "INFO", 0.08)
            build_generated_scene(context, plan)
            self._plan = plan
            _prepare_start_behavior(context, settings, plan)
            write_plan(context.scene, settings, plan)
            self._batch_index = 0
            settings.cancel_requested = False
            self._start_batch(context)
        except Exception as exc:
            if self._plan is not None:
                _finish_timeline(context.scene, settings, self._plan, completed=False)
            _set_status(settings, "ERROR", f"自动导演启动失败：{exc}", "ERROR", 0.0)
            self.report({"ERROR"}, settings.status_message)
            return {"CANCELLED"}

        self._started_at = time.monotonic()
        self._timer = context.window_manager.event_timer_add(0.5, window=context.window)
        context.window_manager.modal_handler_add(self)
        _set_status(settings, "RUNNING", self._running_message(), "INFO", 0.20)
        return {"RUNNING_MODAL"}

    def _batch(self):
        return self._plan["generation_batches"][self._batch_index]

    def _running_message(self):
        return "当前 Clip · Proscenium 正在生成动作"

    def _start_batch(self, context):
        settings = context.scene.baw_auto_director
        batch = self._batch()
        _set_status(
            settings,
            "RUNNING",
            f"正在配置当前 Clip：{batch['title']}",
            "INFO",
            0.18,
        )
        proscenium = _configure_integrations(context, settings, self._plan, batch)
        if bool(getattr(proscenium, "is_generating", False)):
            raise RuntimeError("Proscenium 已有生成任务正在运行")
        self._start_motion(context)

    def _start_motion(self, context):
        context.scene.frame_set(int(self._batch()["local_frame_start"]))
        result = bpy.ops.proscenium.generate("INVOKE_DEFAULT")
        if result not in ({"RUNNING_MODAL"}, {"FINISHED"}):
            raise RuntimeError(f"Proscenium 未启动生成：{result}")
        self._started_at = time.monotonic()

    def _restore_global_timeline(self, context, *, completed: bool):
        if self._plan is None:
            return
        _finish_timeline(
            context.scene,
            context.scene.baw_auto_director,
            self._plan,
            completed=completed,
        )

    def _finish(self, context, result):
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        return result

    def modal(self, context, event):
        settings = context.scene.baw_auto_director
        proscenium = getattr(context.scene, "proscenium", None)
        if settings.cancel_requested or event.type == "ESC":
            if _operator_available("proscenium.cancel"):
                try:
                    bpy.ops.proscenium.cancel("EXEC_DEFAULT")
                except RuntimeError:
                    pass
            settings.cancel_requested = False
            self._restore_global_timeline(context, completed=False)
            _set_status(settings, "CANCELLED", "自动导演已取消；已搭建场景保留供检查", "WARNING", 0.0)
            return self._finish(context, {"CANCELLED"})
        if event.type != "TIMER":
            return {"PASS_THROUGH"}
        if proscenium is None:
            self._restore_global_timeline(context, completed=False)
            _set_status(settings, "ERROR", "Proscenium 场景状态丢失", "ERROR", 0.0)
            return self._finish(context, {"CANCELLED"})
        if bool(getattr(proscenium, "is_generating", False)):
            elapsed = time.monotonic() - self._started_at
            batch_fraction = self._batch_index / len(self._plan["generation_batches"])
            pulse = min(0.78, 0.18 + 0.60 * batch_fraction + min(elapsed / 180.0, 1.0) * 0.12)
            _set_status(settings, "RUNNING", f"{self._running_message()} · {elapsed:.0f} 秒", "INFO", pulse)
            return {"RUNNING_MODAL"}
        quota = str(getattr(proscenium, "quota_exceeded_message", "") or "").strip()
        if quota:
            self._restore_global_timeline(context, completed=False)
            _set_status(settings, "ERROR", f"Proscenium 配额错误：{quota}", "ERROR", 0.0)
            return self._finish(context, {"CANCELLED"})
        if not bool(getattr(proscenium, "is_previewing", False)):
            self._restore_global_timeline(context, completed=False)
            _set_status(settings, "ERROR", "动作生成结束但没有可接受的预览；请检查 Proscenium 状态", "ERROR", 0.0)
            return self._finish(context, {"CANCELLED"})
        if not settings.auto_accept_motion:
            self._restore_global_timeline(context, completed=True)
            _set_status(settings, "PREVIEW_READY", "动作预览已就绪；检查后点击“接受预览并输出到角色”", "READY", 0.82)
            return self._finish(context, {"FINISHED"})
        _set_status(settings, "RUNNING", "正在接受预览并由 Motion Bridge 输出到角色", "INFO", 0.84)
        bridge = context.scene.ba_motion_bridge_settings
        try:
            _resolve_auto_target_switch(context, bridge, settings.target_rig)
        except RuntimeError as exc:
            self._restore_global_timeline(context, completed=False)
            _set_status(settings, "ERROR", f"动作生成成功，但切换角色失败：{exc}", "ERROR", 0.82)
            return self._finish(context, {"CANCELLED"})
        bridge.accept_preview_on_run = True
        try:
            result = bpy.ops.ba_motion_bridge.accept_and_retarget("EXEC_DEFAULT")
        except RuntimeError as exc:
            self._restore_global_timeline(context, completed=False)
            _set_status(settings, "ERROR", f"动作生成成功，但角色输出失败：{exc}", "ERROR", 0.82)
            return self._finish(context, {"CANCELLED"})
        if result != {"FINISHED"}:
            self._restore_global_timeline(context, completed=False)
            _set_status(settings, "ERROR", f"动作生成成功，但角色输出未完成：{result}", "ERROR", 0.82)
            return self._finish(context, {"CANCELLED"})
        try:
            action = bpy.data.actions.get(bridge.last_output_action)
            _preserve_previous_clip(settings, action)
            _apply_continuity_pose(context.scene, settings, action)
            _associate_generated_action(context.scene, settings, action)
        except Exception as exc:
            self._restore_global_timeline(context, completed=False)
            _set_status(settings, "ERROR", f"首帧衔接失败：{exc}", "ERROR", 0.82)
            return self._finish(context, {"CANCELLED"})
        self._restore_global_timeline(context, completed=True)
        _set_status(settings, "COMPLETE", f"当前 Clip 已完成：{self._plan['timing_summary']}；请检查后再输入下一段", "READY", 1.0)
        self.report({"INFO"}, settings.status_message)
        return self._finish(context, {"FINISHED"})


CLASSES = (
    BAW_PG_auto_director,
    BAW_OT_auto_prompt_new,
    BAW_OT_auto_prompt_unlink,
    BAW_OT_auto_prompt_edit,
    BAW_OT_auto_compile_plan,
    BAW_OT_auto_build_scene,
    BAW_OT_auto_remap_existing,
    BAW_OT_auto_import_existing,
    BAW_OT_auto_import_all_existing,
    BAW_OT_auto_finalize_preview,
    BAW_OT_auto_cancel,
    BAW_OT_auto_clear_scene,
    BAW_OT_auto_run,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.baw_auto_director = PointerProperty(type=BAW_PG_auto_director)
    if _sync_reuse_selection_on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_sync_reuse_selection_on_load)
    for scene in getattr(bpy.data, "scenes", ()):
        _sync_reuse_selection(scene)


def unregister():
    if _sync_reuse_selection_on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_sync_reuse_selection_on_load)
    if hasattr(bpy.types.Scene, "baw_auto_director"):
        del bpy.types.Scene.baw_auto_director
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
