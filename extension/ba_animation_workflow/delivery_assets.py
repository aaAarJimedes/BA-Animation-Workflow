"""Conservative dependency audit and reversible packing of local media.

Never saves a blend, edits animation, purges IDs, or writes unpacked files.
LibraryWeakReference is append provenance, not a live library dependency.
"""
import json
import os
from collections import Counter
from datetime import datetime, timezone

import bpy


REPORT_NAME = 'BAW_外部资源检查'
_PACK_COLLECTIONS = ('images', 'sounds', 'fonts')


class AssetPackError(RuntimeError):
    def __init__(self, message, report):
        super().__init__(message)
        self.report = report


def _absolute(path, owner=None):
    if not path:
        return ''
    return os.path.normpath(bpy.path.abspath(path, library=getattr(owner, 'library', None)))


def _key(path):
    return os.path.normcase(os.path.normpath(path)) if path else ''


def _packed(owner):
    return bool(getattr(owner, 'packed_file', None) or getattr(owner, 'packed_files', ()))


def _all_ids():
    for prop in bpy.data.bl_rna.properties:
        if prop.type == 'COLLECTION':
            for block in getattr(bpy.data, prop.identifier, ()):
                if isinstance(block, bpy.types.ID):
                    yield block


def inspect_assets():
    """Read-only, JSON-serializable report; no disk writes or scene evaluation."""
    assets, known_paths, history = [], set(), {}

    def add(kind, owner, path='', status=None, note='', collection='', name=None):
        absolute = _absolute(path, owner)
        if absolute:
            known_paths.add(_key(absolute))
        if status is None:
            status = 'EXTERNAL' if absolute and os.path.exists(absolute) else 'MISSING'
        item = dict(kind=kind, name=name or getattr(owner, 'name', ''), path=path,
                    absolute_path=absolute, status=status, note=note)
        if collection:
            item['collection'] = collection
        assets.append(item)
        return item

    blocks = list(_all_ids())
    live_libraries = {block.library for block in blocks if block.library}
    for library in tuple(live_libraries):
        parent = library.parent
        while parent and parent not in live_libraries:
            live_libraries.add(parent)
            parent = parent.parent
    for block in blocks:
        weak = getattr(block, 'library_weak_reference', None)
        if weak:
            path = _absolute(weak.filepath)
            history.setdefault(path, []).append(block.name)

    for image in bpy.data.images:
        path = image.filepath
        source = image.source
        if source == 'VIEWER':
            add('IMAGE', image, status='INTERNAL', note='渲染/合成临时图像，不是交付依赖')
        elif _packed(image) and source not in {'SEQUENCE', 'MOVIE', 'TILED'}:
            add('IMAGE', image, path, 'PACKED', '已内嵌；旧外部路径失效不表示缺失')
        elif source == 'GENERATED':
            add('IMAGE', image, status='REVIEW' if image.is_dirty else 'INTERNAL',
                note='生成图像；有像素编辑时请手动打包并重新打开核对' if image.is_dirty else '内部生成图像')
        elif source == 'TILED':
            # Even packed UDIMs require complete tile coverage, not packed_file != None.
            known_paths.add(_key(_absolute(path, image)))
            packed_paths = {_key(_absolute(p.filepath, image)) for p in image.packed_files}
            for tile in image.tiles:
                number = tile.number
                tile_path = path.replace('<UDIM>', str(number)).replace(
                    '<UVTILE>', 'u%d_v%d' % ((number - 1001) % 10 + 1, (number - 1001) // 10 + 1))
                tile_abs = _absolute(tile_path, image)
                add('UDIM_TILE', image, tile_path,
                    'PACKED' if _key(tile_abs) in packed_paths else None,
                    'UDIM 分块需逐块核验；未内嵌的分块请随工程交付', name=f'{image.name}:{number}')
        elif source in {'SEQUENCE', 'MOVIE'}:
            add('IMAGE_' + source, image, path, note='不能由此工具内嵌；序列只检查入口帧，完整帧范围需另外核验')
        elif image.library:
            add('LINKED_IMAGE', image, path, 'REVIEW', '属于链接库，需在库源工程中打包并复核')
        elif image.is_dirty or image.use_multiview:
            add('IMAGE', image, path, 'REVIEW', '未保存的像素编辑或多视图需手动确认；不会覆盖当前像素')
        else:
            add('IMAGE', image, path,
                'PACKABLE' if path and os.path.isfile(_absolute(path, image)) else 'MISSING',
                collection='images')

    for collection in ('sounds', 'fonts'):
        for block in getattr(bpy.data, collection):
            path = block.filepath
            if collection == 'fonts' and path == '<builtin>':
                add('FONT', block, status='INTERNAL', note='Blender 内置字体')
            elif _packed(block):
                add(collection.upper(), block, path, 'PACKED', '资源已内嵌')
            elif block.library:
                add(collection.upper(), block, path, 'REVIEW', '链接库资源需在库源工程中处理')
            else:
                add(collection.upper(), block, path,
                    'PACKABLE' if path and os.path.isfile(_absolute(path, block)) else 'MISSING',
                    collection=collection)

    for library in bpy.data.libraries:
        if library not in live_libraries:
            add('LIBRARY', library, library.filepath, 'INTERNAL',
                '当前没有数据块引用此库；追加操作遗留的库记录不是交付依赖')
            continue
        add('LIBRARY', library, library.filepath,
            'PACKED' if library.packed_file else None,
            '真实链接库；此工具不改为本地数据。未内嵌时需随工程交付或使用 Blender 打包链接库后复核')
    for collection in ('movieclips', 'cache_files', 'volumes'):
        for block in getattr(bpy.data, collection, ()):
            path = block.filepath
            if not path and collection == 'volumes':
                continue  # A volume generated by a modifier has no source file.
            note = '需随工程交付；动态序列/缓存的完整范围需另外核验'
            add(collection.upper(), block, path, 'PACKED' if _packed(block) else None, note)
            if collection == 'cache_files':
                for layer in block.layers:
                    add('CACHE_LAYER', block, layer.filepath, note=note)

    seen_caches = set()

    def inspect_cache(cache, owner):
        if not cache or cache.as_pointer() in seen_caches:
            return
        seen_caches.add(cache.as_pointer())
        if cache.use_external or cache.use_disk_cache:
            add('POINT_CACHE', owner, cache.filepath,
                None if cache.filepath else 'REVIEW',
                '磁盘物理缓存不能内嵌；目录存在也不证明烘焙完整。隐式缓存目录需人工确认')

    for scene in bpy.data.scenes:
        if scene.rigidbody_world:
            inspect_cache(scene.rigidbody_world.point_cache, scene)
        editor = scene.sequence_editor
        if editor:
            for strip in editor.strips_all:
                if strip.type == 'MOVIE':
                    add('VSE_MOVIE', scene, strip.filepath, note='视频序列编辑器外部片段', name=strip.name)
                elif strip.type == 'IMAGE':
                    for element in strip.elements:
                        add('VSE_IMAGE', scene, os.path.join(strip.directory, element.filename),
                            note='视频序列编辑器图像元素；需随工程交付', name=strip.name)
    for obj in bpy.data.objects:
        for modifier in obj.modifiers:
            inspect_cache(getattr(modifier, 'point_cache', None), obj)
            domain = getattr(modifier, 'domain_settings', None)
            if domain:
                add('FLUID_CACHE', obj, domain.cache_directory,
                    note='流体缓存目录需随工程交付，尚未逐帧验证内容')
            if modifier.type == 'NODES':
                for bake in modifier.bakes:
                    target = modifier.bake_target if bake.bake_target == 'INHERIT' else bake.bake_target
                    name = f'{obj.name}/{modifier.name}/{bake.bake_id}'
                    if target == 'DISK':
                        path = bake.directory if bake.use_custom_path else modifier.bake_directory
                        add('GEOMETRY_NODES_CACHE', obj, path,
                            None if path else 'REVIEW',
                            '几何节点磁盘烘焙：核对单项/嵌套烘焙路径，尚未逐帧验证缓存内容', name=name)
                    else:
                        # A PACKED target is a setting, not proof that a bake
                        # exists. RNA does not expose its embedded payload here.
                        add('GEOMETRY_NODES_CACHE', obj, status='REVIEW', name=name,
                            note='几何节点设置为内嵌烘焙，但尚未验证烘焙实际存在且完整；需保存重开验证')
        for system in obj.particle_systems:
            inspect_cache(system.point_cache, obj)

    # Blender's own dependency enumerator catches additional file types such as
    # external text/scripts. Exclude historical append origins only after live
    # resources have been classified, so a genuine missing library still fails.
    history_keys = {_key(path) for path in history}
    try:
        for path in bpy.utils.blend_paths(absolute=True, packed=False, local=False):
            absolute = _absolute(path)
            if _key(absolute) not in known_paths | history_keys:
                add('OTHER_EXTERNAL', None, path, note='Blender 报告的其他外链；此工具不自动打包')
    except Exception as exc:
        add('SCAN_ERROR', None, status='REVIEW', note=f'Blender 外链枚举未完成：{exc}')

    summary = dict(Counter(item['status'] for item in assets))
    for status in ('PACKED', 'PACKABLE', 'MISSING', 'EXTERNAL', 'REVIEW', 'INTERNAL'):
        summary.setdefault(status, 0)
    return dict(schema_version=1, blend_filepath=bpy.data.filepath,
                generated_at=datetime.now(timezone.utc).isoformat(), assets=assets, summary=summary,
                all_detected_dependencies_embedded=not any(summary[s] for s in ('PACKABLE', 'MISSING', 'EXTERNAL', 'REVIEW')),
                historical_sources=[dict(path=p, ids=names, note='追加数据的历史来源，不是当前外部依赖') for p, names in history.items()],
                limitations=['检查当前文件中 Blender 可枚举的资源；不保证插件自定义字符串路径已覆盖',
                             '不验证物理烘焙正确性、序列完整帧范围、外部缓存内容或画面效果',
                             '打包仅修改当前内存；需要用户另存并重新打开，才能验证可迁移交付'])


def _pack_one(block):
    block.pack()


def pack_assets():
    """Pack supported local media after preflight; roll back new packs on error.

    External libraries, movie/sequence/cache files remain explicit report items.
    No saving, path relocation, pixel editing, or deletion is performed.
    """
    before = inspect_assets()
    if before['summary']['MISSING'] or any(item['kind'] == 'SCAN_ERROR' for item in before['assets']):
        raise AssetPackError('存在缺失依赖；已在打包前停止，详见资源报告', before)
    candidates = []
    try:
        for item in before['assets']:
            if item['status'] != 'PACKABLE':
                continue
            block = getattr(bpy.data, item['collection']).get(item['name'])
            if block is None or block.library or _packed(block):
                raise RuntimeError('资源状态在检查后改变，请重新检查')
            # Read every candidate before the first mutation. Stream in chunks so
            # large texture sets do not create a second full in-memory copy.
            with open(item['absolute_path'], 'rb') as handle:
                while handle.read(1024 * 1024):
                    pass
            candidates.append((block, block.filepath))
    except Exception as exc:
        before['operation'] = dict(status='PREFLIGHT_FAILED', error=str(exc))
        raise AssetPackError(f'资源预检失败，未执行打包：{exc}', before) from exc

    attempted = []
    try:
        for block, path in candidates:
            attempted.append((block, path))  # Include a pack call that partially fails.
            _pack_one(block)
            if not _packed(block):
                raise RuntimeError(f'{block.name} 未产生内嵌数据')
    except Exception as exc:
        rollback_errors = []
        for block, path in reversed(attempted):
            try:
                if _packed(block):
                    block.unpack(method='REMOVE')  # Discard embedded copy, never write to disk.
                block.filepath = path
            except Exception as rollback_exc:
                rollback_errors.append(f'{block.name}: {rollback_exc}')
        report = inspect_assets()
        report['operation'] = dict(status='ROLLBACK_FAILED' if rollback_errors else 'ROLLED_BACK',
                                   error=str(exc), rollback_errors=rollback_errors)
        message = '打包失败；本轮新增内嵌数据已回退' if not rollback_errors else '打包失败且部分回退失败；请勿覆盖原工程，详见报告'
        raise AssetPackError(message, report) from exc
    after = inspect_assets()
    after['operation'] = dict(status='PACKED_IN_MEMORY', packed_count=len(candidates), saved=False)
    return after


def write_report(report):
    text = bpy.data.texts.get(REPORT_NAME) or bpy.data.texts.new(REPORT_NAME)
    text.clear()
    text.write(json.dumps(report, ensure_ascii=False, indent=2))
    return text


class BAW_OT_inspect_assets(bpy.types.Operator):
    bl_idname = 'baw.inspect_assets'
    bl_label = '检查外部资源'
    bl_description = '检查真实外链、缺失资源及追加历史来源；不改场景数据，报告写入文本'

    def execute(self, context):
        report = inspect_assets()
        text = write_report(report)
        counts = report['summary']
        self.report({'INFO'}, f'缺失 {counts["MISSING"]}，可打包 {counts["PACKABLE"]}，外部/待核验 {counts["EXTERNAL"] + counts["REVIEW"]}；文本：{text.name}')
        return {'FINISHED'}


class BAW_OT_pack_assets(bpy.types.Operator):
    bl_idname = 'baw.pack_assets'
    bl_label = '安全打包可支持资源'
    bl_description = '预检后将普通图片、声音、字体内嵌到内存；不保存、不处理序列/视频/缓存/链接库'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            report = pack_assets()
        except AssetPackError as exc:
            write_report(exc.report)
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        text = write_report(report)
        count = report['operation']['packed_count']
        remain = sum(report['summary'][s] for s in ('MISSING', 'PACKABLE', 'EXTERNAL', 'REVIEW'))
        self.report({'WARNING'} if remain else {'INFO'},
                    f'已在内存打包 {count} 项，仍需处理 {remain} 项；尚未保存。文本：{text.name}')
        return {'FINISHED'}


CLASSES = (BAW_OT_inspect_assets, BAW_OT_pack_assets)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
