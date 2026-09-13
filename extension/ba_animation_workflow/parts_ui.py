"""Reviewable part proposals, face corrections and reversible result switching."""
import json
import bpy
import bmesh
from bpy.props import BoolProperty, CollectionProperty, IntProperty, PointerProperty, StringProperty
from . import parts


class BAW_PG_part_source(bpy.types.PropertyGroup):
    object: PointerProperty(type=bpy.types.Object)
    signature: StringProperty()
    labels: StringProperty()
    review_faces: StringProperty()
    preview_hidden: BoolProperty()
    original_hidden: BoolProperty()
    original_disabled: BoolProperty()
    original_render: BoolProperty()


class BAW_PG_part_group(bpy.types.PropertyGroup):
    group_id: IntProperty()
    label: StringProperty(name='部件名称')
    enabled: BoolProperty(name='分离', default=False)
    faces: IntProperty()
    review: IntProperty()


class BAW_PG_parts(bpy.types.PropertyGroup):
    target: PointerProperty(name='人物', type=bpy.types.Object, poll=lambda self, obj: obj.type in {'MESH', 'ARMATURE'})
    analyzed_target: PointerProperty(type=bpy.types.Object)
    sources: CollectionProperty(type=BAW_PG_part_source)
    groups: CollectionProperty(type=BAW_PG_part_group)
    active: IntProperty(default=0, min=0)
    show_help: BoolProperty(name='使用说明', default=False)
    preview: PointerProperty(type=bpy.types.Collection)
    result: PointerProperty(type=bpy.types.Collection)
    showing_result: BoolProperty()
    shading: StringProperty()
    status: StringProperty()


def source_data(settings):
    if not settings.sources: raise ValueError('请先识别部件')
    if settings.analyzed_target and settings.target != settings.analyzed_target:
        raise ValueError('人物目标已更换，请重新识别；旧分组不会用于新人物')
    if any(not s.object for s in settings.sources):
        raise ValueError('原网格已被删除，请重新识别')
    return [(s.object, s.signature, json.loads(s.labels)) for s in settings.sources]


def active_group(settings):
    if not 0 <= settings.active < len(settings.groups):
        raise ValueError('请选择有效部件')
    return settings.groups[settings.active]


def names_for(settings):
    return {p.group_id: p.label or f'部件 {p.group_id}' for p in settings.groups}


def clear_preview(context, settings):
    changed = bool(settings.preview)
    if settings.preview:
        collection = settings.preview
        settings.preview = None
        parts.discard(collection)
        for source in settings.sources:
            if source.object:
                source.object.hide_viewport = source.preview_hidden
    if settings.shading:
        try:
            old = json.loads(settings.shading)
            screen = bpy.data.screens.get(old['screen'])
            area = screen.areas[old['area']] if screen else None
            if area and area.type == 'VIEW_3D' and area.spaces.active.shading.type == 'SOLID' and area.spaces.active.shading.color_type == 'MATERIAL':
                area.spaces.active.shading.type = old['type']
                area.spaces.active.shading.color_type = old['color']
        except (KeyError, IndexError, ValueError): pass
        settings.shading = ''
    if changed:
        context.view_layer.update()


def show_original(context, settings):
    clear_preview(context, settings)
    if settings.result and settings.showing_result:
        for obj in list(settings.result.all_objects):
            obj.hide_viewport = True; obj.hide_render = True
        for source in settings.sources:
            if source.object:
                source.object.hide_viewport = source.original_disabled
                source.object.hide_render = source.original_render
        settings.showing_result = False
        context.view_layer.update()


def recount(settings):
    counts = {}
    reviews = {}
    for _, _, labels in source_data(settings):
        for group in labels: counts[group] = counts.get(group, 0) + 1
    for source in settings.sources:
        labels = json.loads(source.labels)
        if source.review_faces:
            for i in json.loads(source.review_faces):
                group = labels[i]
                reviews[group] = reviews.get(group, 0) + 1
    for group in settings.groups:
        group.faces = counts.get(group.group_id, 0)
        group.review = (reviews.get(group.group_id, 0) if all(s.review_faces for s in settings.sources)
                        else min(group.review, group.faces))


def _error(operator, settings, exc):
    settings.status = str(exc)
    operator.report({'ERROR'}, str(exc))
    return {'CANCELLED'}


class BAW_UL_parts(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.prop(item, 'enabled', text='')
        row.prop(item, 'label', text='', emboss=False)
        row.label(text=str(item.faces), icon='QUESTION' if item.review else 'NONE')


class BAW_OT_parts_target(bpy.types.Operator):
    bl_idname = 'baw.parts_use_active'
    bl_label = '使用当前对象'
    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type not in {'MESH', 'ARMATURE'}:
            self.report({'ERROR'}, '请选择人物网格或骨架'); return {'CANCELLED'}
        context.scene.baw_parts.target = obj
        return {'FINISHED'}


class BAW_OT_parts_analyze(bpy.types.Operator):
    bl_idname = 'baw.parts_analyze'
    bl_label = '识别可拆分部件'
    bl_description = '按材质名称、位置、脚骨权重及相连网格提出分组；不调用图像 AI，不判断身体完整性'
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        s = context.scene.baw_parts
        try:
            show_original(context, s)
            target = s.target or context.active_object
            objects = parts.sources_for(target, context.scene)
            result, stats, details = parts.analyze(objects)
            s.sources.clear(); s.groups.clear(); s.result = None
            s.target = target; s.analyzed_target = target
            for record in result:
                source = s.sources.add(); source.object = record['object']
                source.signature = record['fingerprint']; source.labels = json.dumps(record['labels'])
                source.review_faces = json.dumps(record.get('review_faces', []))
            for group in sorted(parts.GROUPS):
                item = s.groups.add(); item.group_id = group; item.label = parts.GROUPS[group][0]
                item.faces = stats.get(group, 0); item.enabled = group in {3, 4, 5}
                item.review = sum(x['faces'] for x in details if x['group'] == group and x['confidence'] < .7)
            s.active = next((i for i, g in enumerate(s.groups) if g.enabled and g.faces), 0)
            report = bpy.data.texts.get('BA 部件识别报告') or bpy.data.texts.new('BA 部件识别报告')
            report.clear(); report.write(json.dumps({'method': '本地规则候选，不含图像识别', 'components': details,
                'limitations': ['共用贴图/身体上绘制服饰不能自动识别', '鞋袜、接触身体的小饰品需要复核',
                                '左右按骨架静置坐标推断；无标准骨名时按局部 X 轴', '不自动补身体，不迁移服饰物理到其他骨架']}, ensure_ascii=False, indent=2))
            s.status = '识别完成：先预览、修正分组，再分离勾选部件。问号项需重点核对。'
            return {'FINISHED'}
        except Exception as exc: return _error(self, s, exc)


class BAW_OT_parts_preview(bpy.types.Operator):
    bl_idname = 'baw.parts_preview'
    bl_label = '彩色预览 / 关闭预览'
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        s = context.scene.baw_parts
        try:
            if s.preview:
                clear_preview(context, s); s.status = '已关闭预览，原材质保持不变'; return {'FINISHED'}
            show_original(context, s)
            sources = source_data(s); collection = parts.preview(context.scene, sources, names_for(s))
            s.preview = collection
            for source in s.sources:
                source.preview_hidden = source.object.hide_viewport; source.object.hide_viewport = True
            if context.area and context.area.type == 'VIEW_3D':
                shading = context.space_data.shading
                s.shading = json.dumps(dict(screen=context.screen.name, area=list(context.screen.areas).index(context.area), type=shading.type, color=shading.color_type))
                shading.type = 'SOLID'; shading.color_type = 'MATERIAL'
            s.status = '同色为同一部件。预览只影响视口，正式渲染仍使用原模型。'
            return {'FINISHED'}
        except Exception as exc:
            clear_preview(context, s)
            return _error(self, s, exc)


class BAW_OT_parts_select(bpy.types.Operator):
    bl_idname = 'baw.parts_select'
    bl_label = '选中此部件的面'
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        s = context.scene.baw_parts
        try:
            show_original(context, s)
            if context.object and context.object.mode != 'OBJECT': bpy.ops.object.mode_set(mode='OBJECT')
            sources = source_data(s); parts.validate(sources)
            group = active_group(s).group_id
            for obj in context.selected_objects: obj.select_set(False)
            targets = []
            for obj, _, labels in sources:
                if group not in labels: continue
                obj.hide_set(False); obj.select_set(True); targets.append(obj)
                for v in obj.data.vertices: v.select = False
                for e in obj.data.edges: e.select = False
                for f, label in zip(obj.data.polygons, labels): f.hide = False; f.select = label == group
            if not targets: raise ValueError('此部件没有面')
            context.view_layer.objects.active = targets[0]
            context.tool_settings.mesh_select_mode = (False, False, True)
            bpy.ops.object.mode_set(mode='EDIT')
            s.status = '可补选或取消误选，再点击“用选中面替换此部件”'
            return {'FINISHED'}
        except Exception as exc: return _error(self, s, exc)


class BAW_OT_parts_assign(bpy.types.Operator):
    bl_idname = 'baw.parts_assign'
    bl_label = '将选中面归入此部件'
    bl_options = {'REGISTER', 'UNDO'}
    replace: BoolProperty(default=False, options={'HIDDEN'})
    def execute(self, context):
        s = context.scene.baw_parts
        try:
            if context.mode != 'EDIT_MESH': raise ValueError('请先在编辑模式选中需要归组的面')
            selections = {}
            for source in s.sources:
                obj = source.object
                if obj and obj.mode == 'EDIT':
                    bm = bmesh.from_edit_mesh(obj.data); bm.faces.index_update()
                    selections[obj] = [f.index for f in bm.faces if f.select]
            if not any(selections.values()) and not self.replace: raise ValueError('没有选中面')
            bpy.ops.object.mode_set(mode='OBJECT')
            parts.validate(source_data(s))
            group = active_group(s).group_id
            for source in s.sources:
                labels = json.loads(source.labels)
                if self.replace: labels = [0 if x == group else x for x in labels]
                for i in selections.get(source.object, []): labels[i] = group
                source.labels = json.dumps(labels)
                if source.review_faces:
                    confirmed = set(selections.get(source.object, []))
                    source.review_faces = json.dumps([i for i in json.loads(source.review_faces) if i not in confirmed])
            recount(s)
            s.status = '已更新人工分组；可重新彩色预览检查'
            return {'FINISHED'}
        except Exception as exc: return _error(self, s, exc)


class BAW_OT_parts_add(bpy.types.Operator):
    bl_idname = 'baw.parts_add_group'
    bl_label = '新增部件分组'
    bl_options = {'REGISTER', 'UNDO'}
    label: StringProperty(name='名称', default='新部件')
    def invoke(self, context, event): return context.window_manager.invoke_props_dialog(self)
    def execute(self, context):
        s = context.scene.baw_parts
        if not s.sources: return _error(self, s, ValueError('请先识别部件'))
        try: source_data(s)
        except ValueError as exc: return _error(self, s, exc)
        group = s.groups.add(); group.group_id = max([p.group_id for p in s.groups] + [max(parts.GROUPS)]) + 1
        group.label = self.label.strip() or '新部件'; group.enabled = True
        s.active = len(s.groups) - 1
        return {'FINISHED'}


class BAW_OT_parts_extract(bpy.types.Operator):
    bl_idname = 'baw.parts_extract'
    bl_label = '分离勾选部件（保留原模型）'
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        s = context.scene.baw_parts
        try:
            clear_preview(context, s)
            if s.result: raise ValueError('本轮已生成分离结果；可切换原模型，重新识别后再生成新版本')
            if context.object and context.object.mode != 'OBJECT': bpy.ops.object.mode_set(mode='OBJECT')
            sources = source_data(s)
            selected = {p.group_id for p in s.groups if p.enabled and p.faces}
            result, objects = parts.extract(context, sources, names_for(s), selected)
            s.result = result
            for source in s.sources:
                source.original_hidden = source.object.hide_get(); source.original_render = source.object.hide_render
                source.original_disabled = source.object.hide_viewport
                source.object.hide_viewport = True; source.object.hide_render = True
            for obj in objects:
                source = next(x for x in s.sources if x.object.name == obj['baw_part_source'])
                obj['baw_part_hidden'] = source.original_hidden; obj['baw_part_render_hidden'] = source.original_render
                obj['baw_part_disabled'] = source.original_disabled
                obj.hide_viewport = source.original_disabled
                obj.hide_set(source.original_hidden); obj.hide_render = source.original_render
            s.showing_result = True
            s.status = f'已生成 {len(objects)} 个对象，原网格保留并隐藏。顶点、形态键、UV、权重、材质及绑定核对通过；请检查取下后的身体覆盖。'
            return {'FINISHED'}
        except Exception as exc: return _error(self, s, exc)


class BAW_OT_parts_switch(bpy.types.Operator):
    bl_idname = 'baw.parts_switch'
    bl_label = '切换原模型 / 分离结果'
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        s = context.scene.baw_parts
        if not s.result: return _error(self, s, ValueError('还没有分离结果'))
        if s.showing_result:
            show_original(context, s); s.status = '已切回原模型，分离结果保留并隐藏'
        else:
            clear_preview(context, s)
            for source in s.sources:
                if source.object: source.object.hide_viewport = True; source.object.hide_render = True
            for obj in list(s.result.all_objects):
                obj.hide_viewport = obj.get('baw_part_disabled', False)
                obj.hide_set(obj.get('baw_part_hidden', False)); obj.hide_render = obj.get('baw_part_render_hidden', False)
            s.showing_result = True; s.status = '正在显示分离结果，原模型保留并隐藏'
        return {'FINISHED'}


class BAW_PT_parts(bpy.types.Panel):
    bl_idname = 'BAW_PT_parts'
    bl_label = '人物部件识别与分离'
    bl_parent_id = 'BAW_PT_main'
    bl_category = 'BA 动画'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_options = {'DEFAULT_CLOSED'}
    def draw(self, context):
        from .panels import _wrapped
        l = self.layout; s = context.scene.baw_parts
        l.prop(s, 'target'); l.operator('baw.parts_use_active')
        l.operator('baw.parts_analyze', icon='VIEWZOOM')
        l.prop(s, 'show_help', icon='INFO', toggle=True)
        if s.show_help:
            _wrapped(l, context, '1 识别 → 2 彩色预览并修正 → 3 分离。骨架分析可见蒙皮网格，也可指定单个网格。分离保留原模型，不补出缺失身体或复制物理系统。')
        if s.groups:
            valid = (not s.analyzed_target or s.target == s.analyzed_target) and all(x.object for x in s.sources)
            if not valid:
                _wrapped(l, context, '目标已变化或原网格缺失，请重新识别。', 'ERROR')
            total = sum(g.faces for g in s.groups if g.enabled)
            l.label(text=f'已勾选 {total:,} 个面 · 问号表示需复核')
            l.template_list('BAW_UL_parts', '', s, 'groups', s, 'active', rows=7)
            row = l.row(); row.enabled = valid or bool(s.preview)
            row.operator('baw.parts_preview', text='关闭彩色预览' if s.preview else '彩色预览', icon='MATERIAL')
            col = l.column(align=True); col.enabled = valid and 0 <= s.active < len(s.groups)
            col.operator('baw.parts_select')
            edit = col.column(align=True); edit.enabled = context.mode == 'EDIT_MESH'
            edit.operator('baw.parts_assign')
            edit.operator('baw.parts_assign', text='用选中面替换此部件').replace = True
            col.operator('baw.parts_add_group', icon='ADD')
            row = l.row(); row.enabled = valid and bool(total) and not s.result
            row.operator('baw.parts_extract', icon='MOD_EXPLODE')
            if s.result: l.operator('baw.parts_switch', icon='LOOP_BACK')
            if s.show_help:
                _wrapped(l, context, '鞋袜与小配件需核对；同色为同组。多个网格保留各自形态键，不强制焊接。')
        if s.status: _wrapped(l, context, s.status)


CLASSES = (BAW_PG_part_source, BAW_PG_part_group, BAW_PG_parts, BAW_UL_parts,
           BAW_OT_parts_target, BAW_OT_parts_analyze, BAW_OT_parts_preview, BAW_OT_parts_select,
           BAW_OT_parts_assign, BAW_OT_parts_add, BAW_OT_parts_extract, BAW_OT_parts_switch, BAW_PT_parts)


def register():
    for cls in CLASSES: bpy.utils.register_class(cls)
    bpy.types.Scene.baw_parts = PointerProperty(type=BAW_PG_parts)


def unregister():
    # Only temporary color previews are removed. Finished split results and
    # originals remain available when disabling/reloading the extension.
    for scene in bpy.data.scenes:
        clear_preview(bpy.context, scene.baw_parts)
    del bpy.types.Scene.baw_parts
    for cls in reversed(CLASSES): bpy.utils.unregister_class(cls)
