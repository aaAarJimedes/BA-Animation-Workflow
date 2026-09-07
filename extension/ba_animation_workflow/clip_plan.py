"""One-clip plan compilation; no Blender UI or generation side effects."""
from __future__ import annotations
import uuid
import re
PLAN_SCHEMA = 4

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


def compile_plan(settings, placement_frame: int | None = None) -> dict:
    prompt = _prompt_value(settings)
    if not prompt:
        raise ValueError("请先输入当前 Clip 的动作描述")
    if re.search(r'(?m)^\s*(?:```|(?:mode|prompt|prompt_blocks|pose_anchors|spatial_constraints|characters|root_motion)\s*:)', prompt):
        raise ValueError("请只粘贴当前 Clip 的英文动作内容；帧数填在面板，关键帧和约束需单独设置")
    if len(prompt) > 1000:
        raise ValueError("当前 Clip 提示词超过 Proscenium 的 1000 字符上限；请精简为一个动作段")
    scene = getattr(settings, "id_data", None)
    render = getattr(scene, "render", None)
    if render is not None:
        fps = float(render.fps) / max(float(render.fps_base), 1e-6)
    else:
        fps = float(getattr(settings, "fps", 30))
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
    timing_summary = f"{fps:g} FPS · {frame_count} 帧 · 1 个动作段"
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

