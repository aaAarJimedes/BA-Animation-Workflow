from __future__ import annotations

import json
import math
import os
import stat
import uuid
from pathlib import Path
from typing import Iterable

import bpy
from mathutils import Vector

from .constants import (
    ADDON_VERSION,
    CACHE_MARKER,
    COLLECTIONS,
    EXTERNAL_ADDONS,
    OWNER_KEY,
    OWNER_VALUE,
    PROJECT_FOLDERS,
    ROLE_KEY,
    ROOT_COLLECTION,
    SCENE_ID_KEY,
    TOOL_ID,
    TOOL_NAME,
    WORKSPACE_MARKER,
    WORKSPACE_SCHEMA,
)


def ensure_scene_id(scene: bpy.types.Scene | None = None) -> str:
    scene = scene or bpy.context.scene
    scene_id = scene.get(SCENE_ID_KEY)
    duplicated = isinstance(scene_id, str) and scene_id and any(
        other != scene and other.get(SCENE_ID_KEY) == scene_id for other in bpy.data.scenes
    )
    if not isinstance(scene_id, str) or not scene_id or duplicated:
        scene_id = str(uuid.uuid4())
        scene[SCENE_ID_KEY] = scene_id
    return scene_id


def mark_owned(datablock, role: str, scene_id: str | None = None) -> None:
    datablock[OWNER_KEY] = OWNER_VALUE
    datablock[ROLE_KEY] = role
    if scene_id:
        datablock[SCENE_ID_KEY] = scene_id


def is_owned(datablock, role: str | None = None, scene_id: str | None = None) -> bool:
    if datablock is None or datablock.get(OWNER_KEY) != OWNER_VALUE:
        return False
    if role is not None and datablock.get(ROLE_KEY) != role:
        return False
    if scene_id is not None and datablock.get(SCENE_ID_KEY) != scene_id:
        return False
    return True


def migrate_legacy_scene(scene: bpy.types.Scene) -> bool:
    """Claim only the exact 0.1.0 hierarchy; legacy objects remain untrusted."""
    root = bpy.data.collections.get(ROOT_COLLECTION)
    if root is None or is_owned(root) or root.name not in scene.collection.children:
        return False
    children: dict[str, bpy.types.Collection] = {}
    for name in COLLECTIONS:
        child = bpy.data.collections.get(name)
        if child is None or is_owned(child) or child.name not in root.children:
            return False
        children[name] = child

    scene_id = ensure_scene_id(scene)
    mark_owned(root, ROOT_COLLECTION, scene_id)
    for name, child in children.items():
        mark_owned(child, name, scene_id)
    scene["baw_migrated_from"] = "0.1.0"
    return True


def ensure_collection(
    name: str,
    parent: bpy.types.Collection | None = None,
    scene: bpy.types.Scene | None = None,
) -> bpy.types.Collection:
    scene = scene or bpy.context.scene
    scene_id = ensure_scene_id(scene)
    collection = next(
        (
            item
            for item in bpy.data.collections
            if is_owned(item, role=name, scene_id=scene_id) and item.library is None
        ),
        None,
    )
    if collection is None:
        collection = bpy.data.collections.new(name)
        mark_owned(collection, name, scene_id)

    if parent is None:
        scene_children = scene.collection.children
        if collection.name not in scene_children:
            scene_children.link(collection)
    elif collection.name not in parent.children:
        parent.children.link(collection)
    return collection


def ensure_scene_collections(scene: bpy.types.Scene | None = None) -> dict[str, bpy.types.Collection]:
    scene = scene or bpy.context.scene
    migrate_legacy_scene(scene)
    scene_id = ensure_scene_id(scene)
    for child in tuple(scene.collection.children):
        if (
            is_owned(child, role=ROOT_COLLECTION)
            and child.get(SCENE_ID_KEY) != scene_id
        ):
            scene.collection.children.unlink(child)
    root = ensure_collection(ROOT_COLLECTION, scene=scene)
    result = {ROOT_COLLECTION: root}
    for name in COLLECTIONS:
        result[name] = ensure_collection(name, root, scene=scene)
    return result


def link_only(obj: bpy.types.Object, collection: bpy.types.Collection) -> None:
    if not is_owned(obj) or not is_owned(collection):
        raise ValueError("link_only 仅允许移动本工具拥有的对象和集合")
    if not obj.users_collection:
        collection.objects.link(obj)
        return
    if collection not in obj.users_collection:
        collection.objects.link(obj)
    for existing in tuple(obj.users_collection):
        if existing != collection and is_owned(existing):
            existing.objects.unlink(obj)


def find_owned_object(
    role: str,
    collection: bpy.types.Collection,
    expected_type: str | None = None,
) -> bpy.types.Object | None:
    scene_id = collection.get(SCENE_ID_KEY)
    for obj in bpy.data.objects:
        if not is_owned(obj, role=role, scene_id=scene_id) or obj.library is not None:
            continue
        if expected_type is not None and obj.type != expected_type:
            continue
        return obj
    return None


def ensure_object(
    name: str,
    data,
    collection: bpy.types.Collection,
    expected_type: str | None = None,
) -> bpy.types.Object:
    scene_id = collection.get(SCENE_ID_KEY)
    obj = find_owned_object(name, collection, expected_type)
    if obj is None:
        obj = bpy.data.objects.new(name, data)
        mark_owned(obj, name, scene_id)
    elif data is not None and obj.data is None and obj.type == expected_type:
        obj.data = data
    link_only(obj, collection)
    return obj


def find_character_object(context: bpy.types.Context) -> bpy.types.Object | None:
    active = context.active_object
    if active is None:
        return None
    if active.type in {"ARMATURE", "MESH"}:
        return active
    if active.parent and active.parent.type == "ARMATURE":
        return active.parent
    return active


def find_armature(context: bpy.types.Context) -> bpy.types.Object | None:
    active = context.active_object
    if active is None:
        return None
    if active.type == "ARMATURE":
        return active
    if active.find_armature():
        return active.find_armature()
    if active.parent and active.parent.type == "ARMATURE":
        return active.parent
    return None


def object_bounds_world(obj: bpy.types.Object | None) -> tuple[Vector, float]:
    if obj is None:
        return Vector((0.0, 0.0, 1.0)), 2.0

    candidates = [obj]
    if obj.type == "ARMATURE":
        candidates.extend(child for child in obj.children_recursive if child.type == "MESH")

    points: list[Vector] = []
    for candidate in candidates:
        if candidate.type not in {"MESH", "CURVE", "SURFACE", "FONT", "META", "ARMATURE"}:
            continue
        try:
            points.extend(candidate.matrix_world @ Vector(corner) for corner in candidate.bound_box)
        except (AttributeError, RuntimeError, TypeError):
            continue

    if not points:
        return obj.matrix_world.translation.copy(), 2.0

    lower = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    upper = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    center = (lower + upper) * 0.5
    return center, max(upper.z - lower.z, 0.5)


def point_at(obj: bpy.types.Object, target: Vector) -> None:
    direction = target - obj.matrix_world.translation
    if direction.length_squared > 1e-10:
        obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def iter_action_fcurves(action: bpy.types.Action | None) -> Iterable[bpy.types.FCurve]:
    if action is None:
        return

    legacy = getattr(action, "fcurves", None)
    if legacy is not None:
        yield from legacy
        return

    seen: set[int] = set()
    for layer in getattr(action, "layers", ()):
        for strip in getattr(layer, "strips", ()):
            for channelbag in getattr(strip, "channelbags", ()):
                for fcurve in channelbag.fcurves:
                    pointer = fcurve.as_pointer()
                    if pointer not in seen:
                        seen.add(pointer)
                        yield fcurve


def action_key_count(action: bpy.types.Action | None) -> int:
    return sum(len(curve.keyframe_points) for curve in iter_action_fcurves(action))


def simplify_indices(points: list[tuple[float, float]], tolerance: float) -> set[int]:
    if len(points) <= 2 or tolerance <= 0.0:
        return set(range(len(points)))

    keep = {0, len(points) - 1}
    stack = [(0, len(points) - 1)]
    while stack:
        start, end = stack.pop()
        x0, y0 = points[start]
        x1, y1 = points[end]
        dx = x1 - x0
        max_error = -1.0
        max_index = None
        for index in range(start + 1, end):
            x, y = points[index]
            ratio = (x - x0) / dx if abs(dx) > 1e-12 else 0.0
            interpolated = y0 + ratio * (y1 - y0)
            error = abs(y - interpolated)
            if error > max_error:
                max_error = error
                max_index = index
        if max_index is not None and max_error > tolerance:
            keep.add(max_index)
            stack.append((start, max_index))
            stack.append((max_index, end))
    return keep


def smooth_fcurve(fcurve: bpy.types.FCurve, strength: float, passes: int) -> None:
    if strength <= 0.0 or passes <= 0 or len(fcurve.keyframe_points) < 3:
        return
    for _ in range(passes):
        values = [point.co.y for point in fcurve.keyframe_points]
        smoothed = values[:]
        for index in range(1, len(values) - 1):
            neighbor_average = (values[index - 1] + values[index + 1]) * 0.5
            smoothed[index] = values[index] * (1.0 - strength) + neighbor_average * strength
        for point, value in zip(fcurve.keyframe_points, smoothed):
            point.co.y = value
    fcurve.update()


def unwrap_euler_fcurve(fcurve: bpy.types.FCurve) -> None:
    keyframes = list(fcurve.keyframe_points)
    if len(keyframes) < 2:
        return
    previous = keyframes[0].co.y
    for point in keyframes[1:]:
        original = point.co.y
        value = original
        while value - previous > math.pi:
            value -= math.tau
        while value - previous < -math.pi:
            value += math.tau
        offset = value - original
        if abs(offset) > 1e-12:
            point.co.y = value
            point.handle_left.y += offset
            point.handle_right.y += offset
        previous = value
    fcurve.update()


def simplify_fcurve(fcurve: bpy.types.FCurve, tolerance: float) -> int:
    keyframes = list(fcurve.keyframe_points)
    if len(keyframes) <= 2:
        return 0
    points = [(point.co.x, point.co.y) for point in keyframes]
    keep = simplify_indices(points, tolerance)
    removed = 0
    for index in range(len(keyframes) - 1, -1, -1):
        if index not in keep:
            fcurve.keyframe_points.remove(keyframes[index], fast=True)
            removed += 1
    for point in fcurve.keyframe_points:
        point.handle_left_type = "AUTO_CLAMPED"
        point.handle_right_type = "AUTO_CLAMPED"
    fcurve.update()
    return removed


def module_enabled(token_options: tuple[str, ...]) -> bool:
    modules = tuple(addon.module.lower() for addon in bpy.context.preferences.addons)
    return any(
        any(module == token or module.rsplit(".", 1)[-1] == token for token in token_options)
        for module in modules
    )


def external_addon_status() -> dict[str, bool]:
    # One live snapshot per query; enabling/disabling an extension is visible
    # immediately, without an RNA-object cache or a timer.
    modules = {addon.module.lower() for addon in bpy.context.preferences.addons}
    modules.update(module.rsplit('.', 1)[-1] for module in tuple(modules))
    return {name: any(token in modules for token in tokens)
            for name, tokens in EXTERNAL_ADDONS.items()}


def operator_available(operator) -> bool:
    try:
        operator.get_rna_type()
    except (AttributeError, KeyError, RuntimeError):
        return False
    return True


def _is_reparse_point(path: Path) -> bool:
    try:
        status = os.lstat(path)
    except OSError:
        return False
    attributes = getattr(status, "st_file_attributes", 0)
    return path.is_symlink() or bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _reject_reparse_chain(path: Path) -> None:
    current = path
    while True:
        if os.path.lexists(current) and _is_reparse_point(current):
            raise ValueError(f"路径包含符号链接或目录联接，已拒绝：{current}")
        if current.parent == current:
            break
        current = current.parent


def validate_project_root(path: Path) -> Path:
    absolute = Path(os.path.abspath(path))
    _reject_reparse_chain(absolute)
    root = absolute.resolve()
    if root.parent == root:
        raise ValueError("项目根目录不能是盘符根目录")

    home = Path.home().resolve()
    if root == home:
        raise ValueError(f"项目目录不能直接使用用户主目录：{home}")
    protected_trees = {
        Path(bpy.app.binary_path).resolve().parent,
        Path(bpy.utils.user_resource("CONFIG")).resolve(),
    }
    for protected_root in protected_trees:
        if root == protected_root or protected_root in root.parents:
            raise ValueError(f"项目目录不能位于受保护路径：{protected_root}")
    return root


def resolve_project_root(settings) -> Path | None:
    raw = settings.project_root.strip()
    if not raw:
        return None
    return validate_project_root(Path(bpy.path.abspath(raw)).expanduser())


def _read_json_object(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取所有权标记 {path.name}：{exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"所有权标记格式无效：{path}")
    return payload


def _validate_workspace_payload(payload: dict) -> dict:
    if payload.get("tool_id") != TOOL_ID or payload.get("schema_version") != WORKSPACE_SCHEMA:
        raise ValueError("项目目录存在未知或不兼容的 .baw_workspace，未做覆盖")
    project_id = payload.get("project_id")
    try:
        uuid.UUID(project_id)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("项目标记缺少有效 project_id") from exc
    return payload


def _is_legacy_workspace_payload(payload: dict) -> bool:
    return (
        set(payload).issubset({"tool", "version"})
        and payload.get("tool") == TOOL_NAME
        and payload.get("version") == "0.1.0"
    )


def _new_workspace_identity(migrated_from: str | None = None) -> dict:
    identity = {
        "tool_id": TOOL_ID,
        "tool": TOOL_NAME,
        "schema_version": WORKSPACE_SCHEMA,
        "project_id": str(uuid.uuid4()),
        "version": ".".join(str(part) for part in ADDON_VERSION),
    }
    if migrated_from:
        identity["migrated_from"] = migrated_from
    return identity


def read_workspace_identity(root: Path) -> dict:
    root = validate_project_root(root)
    marker = root / WORKSPACE_MARKER
    if not marker.is_file() or _is_reparse_point(marker):
        raise ValueError("项目所有权标记不存在或不是普通文件")
    return _validate_workspace_payload(_read_json_object(marker))


def _write_cache_marker(cache: Path, identity: dict) -> None:
    marker = cache / CACHE_MARKER
    if os.path.lexists(marker) and _is_reparse_point(marker):
        raise ValueError("缓存所有权标记不能是符号链接或重解析点")
    marker.write_text(
        json.dumps(
            {
                "tool_id": TOOL_ID,
                "schema_version": WORKSPACE_SCHEMA,
                "project_id": identity["project_id"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def ensure_cache_owner(cache: Path, identity: dict, allow_legacy_claim: bool = False) -> None:
    _reject_reparse_chain(cache)
    cache.mkdir(parents=True, exist_ok=True)
    _reject_reparse_chain(cache)
    marker = cache / CACHE_MARKER
    if os.path.lexists(marker) and _is_reparse_point(marker):
        raise ValueError("缓存所有权标记不能是符号链接或重解析点")
    if os.path.lexists(marker):
        payload = _read_json_object(marker)
        if (
            payload.get("tool_id") != TOOL_ID
            or payload.get("schema_version") != WORKSPACE_SCHEMA
            or payload.get("project_id") != identity["project_id"]
        ):
            raise ValueError("缓存所有权标记与项目不匹配")
        return
    if any(cache.iterdir()) and not allow_legacy_claim:
        raise ValueError("缓存目录已有未知内容，拒绝接管")
    _write_cache_marker(cache, identity)


def create_project_folders(root: Path) -> dict:
    root = validate_project_root(root)
    marker = root / WORKSPACE_MARKER
    migrated_legacy = False
    if os.path.lexists(marker) and _is_reparse_point(marker):
        raise ValueError(".baw_workspace 不能是符号链接或重解析点")
    if os.path.lexists(marker):
        if not marker.is_file() or _is_reparse_point(marker):
            raise ValueError(".baw_workspace 不是普通文件，拒绝覆盖")
        payload = _read_json_object(marker)
        if _is_legacy_workspace_payload(payload):
            identity = _new_workspace_identity(migrated_from="0.1.0")
            migrated_legacy = True
        else:
            identity = _validate_workspace_payload(payload)
    else:
        identity = _new_workspace_identity()

    root.mkdir(parents=True, exist_ok=True)
    for relative in PROJECT_FOLDERS:
        destination = root / relative
        _reject_reparse_chain(destination)
        destination.mkdir(parents=True, exist_ok=True)
        _reject_reparse_chain(destination)
    ensure_cache_owner(generated_cache_dir(root), identity, allow_legacy_claim=migrated_legacy)
    if not os.path.lexists(marker) or migrated_legacy:
        marker.write_text(json.dumps(identity, ensure_ascii=False, indent=2), encoding="utf-8")
    return identity


def generated_cache_dir(root: Path) -> Path:
    return root / "50_cache" / "baw_generated"


def cache_is_safe(root: Path, cache: Path) -> bool:
    try:
        root = validate_project_root(root)
        expected = generated_cache_dir(root)
        if Path(os.path.abspath(cache)) != Path(os.path.abspath(expected)):
            return False
        expected.relative_to(root)
        _reject_reparse_chain(expected)
        identity = read_workspace_identity(root)
        cache_marker = expected / CACHE_MARKER
        if not cache_marker.is_file() or _is_reparse_point(cache_marker):
            return False
        payload = _read_json_object(cache_marker)
        return (
            payload.get("tool_id") == TOOL_ID
            and payload.get("schema_version") == WORKSPACE_SCHEMA
            and payload.get("project_id") == identity["project_id"]
        )
    except (OSError, ValueError):
        return False


def recreate_generated_cache(root: Path) -> Path:
    identity = read_workspace_identity(root)
    cache = generated_cache_dir(root)
    cache.mkdir(parents=True, exist_ok=False)
    _write_cache_marker(cache, identity)
    return cache


def build_audit(context: bpy.types.Context) -> dict:
    scene = context.scene
    armature = find_armature(context)
    action = armature.animation_data.action if armature and armature.animation_data else None
    missing_images = []
    for image in bpy.data.images:
        if image.source == "FILE" and image.filepath:
            path = Path(bpy.path.abspath(image.filepath))
            if not path.exists():
                missing_images.append(image.name)

    lights = [obj.name for obj in scene.objects if obj.type == "LIGHT"]
    bridge = getattr(scene, "ba_motion_bridge_settings", None)
    proscenium = getattr(scene, "proscenium", None)
    try:
        bridge_source = bridge.source_rig.name if bridge and bridge.source_rig else None
    except (AttributeError, ReferenceError):
        bridge_source = None
    try:
        bridge_target = bridge.target_rig.name if bridge and bridge.target_rig else None
    except (AttributeError, ReferenceError):
        bridge_target = None
    bridge_temporary = sum(
        1
        for item in (*tuple(bpy.data.actions), *tuple(bpy.data.objects))
        if item.get("bam_owner") in {"proscenium_motion_bridge", "ba_motion_bridge"}
        and item.get("bam_temporary") is True
    )
    ai_motion = {
        "proscenium_generating": bool(proscenium and getattr(proscenium, "is_generating", False)),
        "proscenium_previewing": bool(proscenium and getattr(proscenium, "is_previewing", False)),
        "source": bridge_source,
        "target": bridge_target,
        "mapping": (
            [int(bridge.matched_count), int(bridge.expected_count)] if bridge else [0, 0]
        ),
        "mapping_valid": bool(bridge and bridge.mapping_valid),
        "root_motion_policy": getattr(bridge, "root_motion_policy", None) if bridge else None,
        "root_motion_mode": bridge.root_motion_mode if bridge else None,
        "motion_space": getattr(bridge, "motion_space", None) if bridge else None,
        "end_effector_guard": (
            bool(getattr(bridge, "use_end_effector_guard", False)) if bridge else None
        ),
        "end_effector_guard_strength": (
            float(getattr(bridge, "end_effector_guard_strength", 0.0)) if bridge else None
        ),
        "last_output_action": bridge.last_output_action if bridge else None,
        "recovery_pending": bool(
            bridge
            and (
                bridge.constraint_snapshot_json
                or bridge.previous_target_state_available
            )
        ),
        "temporary_owned_data": bridge_temporary,
    }
    report = {
        "blender": bpy.app.version_string,
        "file": bpy.data.filepath or "<未保存>",
        "frame_range": [scene.frame_start, scene.frame_end],
        "fps": scene.render.fps / scene.render.fps_base,
        "render_engine": scene.render.engine,
        "resolution": [scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage],
        "active_object": context.active_object.name if context.active_object else None,
        "armature": armature.name if armature else None,
        "action": action.name if action else None,
        "action_keys": action_key_count(action),
        "camera": scene.camera.name if scene.camera else None,
        "lights": lights,
        "missing_images": missing_images,
        "external_addons": external_addon_status(),
        "ai_motion": ai_motion,
    }
    warnings = []
    if armature is None:
        warnings.append("未检测到活动角色骨架")
    if action is None:
        warnings.append("活动骨架没有动作")
    if scene.camera is None:
        warnings.append("场景没有活动相机")
    if not lights:
        warnings.append("场景没有灯光")
    if missing_images:
        warnings.append(f"有 {len(missing_images)} 张贴图路径失效")
    if not bpy.data.filepath:
        warnings.append("工程尚未保存")
    if ai_motion["proscenium_generating"]:
        warnings.append("Proscenium 仍在生成，当前结果尚未就绪")
    if ai_motion["proscenium_previewing"]:
        warnings.append("Proscenium 仍处于预览状态，动作尚未接受")
    if ai_motion["recovery_pending"]:
        warnings.append("Motion Bridge 仍保留角色原状态恢复点；交付前确认是否恢复约束/原动画")
    if bridge_temporary:
        warnings.append(f"Motion Bridge 有 {bridge_temporary} 个可安全清理的临时数据块")
    report["warnings"] = warnings
    return report


def write_audit_text(report: dict) -> bpy.types.Text:
    text = bpy.data.texts.get("BAW_检查报告") or bpy.data.texts.new("BAW_检查报告")
    text.clear()
    text.write(json.dumps(report, ensure_ascii=False, indent=2))
    return text
