"""Read-only render preflight and source-bound batch manifests.

This module prepares a plan; it does not start a render or delete old outputs.
"""
import hashlib
import json
from pathlib import Path

import bpy
from bpy.props import IntProperty, StringProperty
from bpy_extras.io_utils import ExportHelper


def frame_batches(start, end, size):
    if any(type(v) is not int for v in (start, end, size)):
        raise ValueError('帧范围和分段长度必须为整数')
    if end < start or size < 1:
        raise ValueError('结束帧不能早于开始帧；分段长度必须大于 0')
    return [{'start': a, 'end': min(a + size - 1, end),
             'frames': min(size, end - a + 1)}
            for a in range(start, end + 1, size)]


def source_digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def check_source(plan):
    """Call before resuming a saved plan. Changed look/source means a new run."""
    p = Path(plan['source'])
    if not p.is_file() or source_digest(p) != plan['source_sha256']:
        raise ValueError('源工程已变化或不存在；创建新计划，不得混用旧分段')


def create_plan(scene, start, end, batch_size):
    if not bpy.data.filepath or bpy.data.is_dirty:
        raise ValueError('请先保存当前工程，再生成与已保存版本绑定的计划')
    if scene.render.fps <= 0 or scene.render.fps_base <= 0:
        raise ValueError('工程帧率无效')
    if scene.frame_step != 1:
        raise ValueError('连续分段要求帧步长为 1；请先核对工程输出设置')
    if scene.rigidbody_world and scene.rigidbody_world.enabled:
        raise ValueError('仍有实时刚体物理；请先完成可独立回放的动作烘焙，保留实际预热')
    simulation = {'CLOTH', 'SOFT_BODY', 'FLUID', 'PARTICLE_SYSTEM', 'DYNAMIC_PAINT'}
    if any(m.type in simulation and m.show_render for o in scene.objects for m in o.modifiers):
        raise ValueError('检测到其他模拟修改器；独立分段前需另行验证缓存随工程可用')
    if any(m.type == 'NODES' and m.node_group and any('Simulation' in n.bl_idname for n in m.node_group.nodes)
           for o in scene.objects for m in o.modifiers):
        raise ValueError('检测到几何节点模拟；独立分段前需验证模拟缓存')
    if not scene.camera:
        raise ValueError('请先设置输出相机')
    source = str(Path(bpy.data.filepath).resolve())
    fps = scene.render.fps / scene.render.fps_base
    from .delivery_assets import inspect_assets
    assets = inspect_assets()
    if not assets['all_detected_dependencies_embedded']:
        raise ValueError('分段源绑定要求实际依赖已内嵌；请先检查并处理外部素材与缓存')
    parts = frame_batches(start, end, batch_size)
    return {
        'schema_version': 1, 'kind': 'render_plan_only', 'source': source,
        'source_sha256': source_digest(source), 'scene': scene.name,
        'fps': scene.render.fps, 'fps_base': scene.render.fps_base,
        'effective_fps': fps, 'start': start, 'end': end,
        'frame_count': end - start + 1, 'duration': (end - start + 1) / fps,
        'scene_timeline': [scene.frame_start, scene.frame_end],
        'resolution': [scene.render.resolution_x, scene.render.resolution_y],
        'resolution_percentage': scene.render.resolution_percentage,
        'engine': scene.render.engine, 'camera': scene.camera.name,
        'samples': scene.cycles.samples if scene.render.engine == 'CYCLES' else None,
        'parts': parts, 'completed_parts': [], 'resource_audit': assets,
        'execution_notes': [
            '这是规划文件，不是渲染完成证明；使用支持该版本计划的外部执行器或按列表手动渲染。',
            '每段使用独立 Blender 进程；TEMP、TMP 和 Blender 临时目录放到选定工作盘。',
            '渲染前验证源哈希；任一画面设置变化后使用新目录与新计划。',
            '未封口的视频不是已完成片段；逐段解码及核对帧数后再更新断点。',
            '音轨意图单独确认；无声版不添加声音，带音轨版本在完整拼接后统一合成。',
            '合成后校验帧率、连续时间戳、帧数、分辨率、音轨和每个接缝。',
            '几何节点或其他未识别的时序依赖仍需人工确认；通过预检不代表物理视觉正确。'
        ]
    }


class BAW_OT_export_render_plan(bpy.types.Operator, ExportHelper):
    bl_idname = 'baw.export_render_plan'
    bl_label = '导出分段渲染计划'
    bl_description = '只生成与已保存源工程绑定的 JSON 计划；不启动渲染，不改变 FPS 或预热帧'
    filename_ext = '.json'
    filter_glob: StringProperty(default='*.json', options={'HIDDEN'})
    start: IntProperty(name='正式开始帧', default=0)
    end: IntProperty(name='正式结束帧', default=250)
    batch_size: IntProperty(name='每段帧数', default=48, min=1, max=10000)

    def invoke(self, context, event):
        self.start, self.end = context.scene.frame_start, context.scene.frame_end
        self.filepath = 'render_plan.json'
        return ExportHelper.invoke(self, context, event)

    def execute(self, context):
        try:
            plan = create_plan(context.scene, self.start, self.end, self.batch_size)
            # No silent replacement of a plan that may own completed segments.
            with open(self.filepath, 'x', encoding='utf8') as stream:
                json.dump(plan, stream, ensure_ascii=False, indent=2)
        except (ValueError, OSError, KeyError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        self.report({'INFO'}, f"已导出 {len(plan['parts'])} 段计划；尚未渲染")
        return {'FINISHED'}


class BAW_PT_delivery(bpy.types.Panel):
    bl_idname = 'BAW_PT_delivery'
    bl_label = '渲染规划与资源交付'
    bl_parent_id = 'BAW_PT_main'
    bl_category = 'BA 动画'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        from .panels import _wrapped
        l = self.layout
        l.operator('baw.inspect_assets', icon='VIEWZOOM')
        l.operator('baw.pack_assets', icon='PACKAGE')
        _wrapped(l, context, '检查报告保留在文本编辑器。打包后请保存工程；移动或改名后重新打开核对。')
        l.separator()
        l.operator('baw.export_render_plan', icon='RENDER_ANIMATION')
        _wrapped(l, context, '先保存，再选择正式出片范围。48 帧为本机案例值；计划不会启动渲染。')


CLASSES = (BAW_OT_export_render_plan, BAW_PT_delivery)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)

