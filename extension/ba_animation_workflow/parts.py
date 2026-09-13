"""Local, inspectable garment proposals and transactional mesh extraction.

No image model or remote service is involved. Semantic guesses never replace
the artist's ability to reassign faces. All topology operations happen on copies.
"""
from __future__ import annotations

from array import array
from collections import Counter, defaultdict
from colorsys import hsv_to_rgb
import hashlib
import json
import math
import re
import struct
import uuid

import bpy
import bmesh
from mathutils import Vector
from mathutils.kdtree import KDTree

GROUPS = {
    0: ('待识别', (.5, .5, .5, 1)),
    1: ('身体', (.9, .62, .43, 1)),
    2: ('头发', (.72, .35, .85, 1)),
    3: ('服装', (.18, .58, .95, 1)),
    4: ('左鞋', (.15, .85, .5, 1)),
    5: ('右鞋', (.95, .5, .12, 1)),
    6: ('饰品', (.95, .82, .15, 1)),
    7: ('左袜', (.52, .85, .78, 1)),
    8: ('右袜', (.88, .64, .62, 1)),
    9: ('下装', (.22, .25, .7, 1)),
}
FACE_ID = 'baw_part_group'
VERT_ID = 'baw_source_vertex'
SOURCE_FACE = 'baw_source_face'
SOURCE_LOOP = 'baw_source_loop'
OWNER = 'baw_parts_owner'


def _text(value):
    return re.sub(r'[\W_]+', '', str(value).lower())


def _role(name):
    t = _text(name)
    if any(w in t for w in ('sock', 'stocking', '袜', '靴下')):
        return 'SOCK'
    if any(w in t for w in ('pants', 'trouser', 'shorts', '裤', 'ズボン')):
        return 'BOTTOM'
    # Explicit garments take priority over generic object names such as body.
    if any(w in t for w in ('shoelace', '鞋带', 'shoe', 'footwear', 'boot', 'sneaker', '靴', '鞋')):
        return 'SHOE'
    if any(w in t for w in ('hairpin', 'hairclip', '发饰', '髪飾', 'earring', '眼镜', 'glasses', '光环', 'halo', '首饰', '耳环')):
        return 'ACCESSORY'
    if any(w in t for w in ('cloth', 'shirt', 'coat', 'jacket', 'dress', 'skirt', 'pants', 'trouser', '衣', '服饰', '服装', '衣料', '裙', 'ズボン', '上着', 'button', 'zipper', '拉链', '纽扣')):
        return 'CLOTH'
    if any(w in t for w in ('hair', '头发', '髪', '前发', '後发')):
        return 'HAIR'
    if any(w in t for w in ('skin', 'body', 'face', 'head', 'eye', 'brow', 'teeth', 'tongue', '身体', '皮肤', '头', '眉', '瞳', '耳朵', '肌')):
        return 'BODY'
    return 'UNKNOWN'


def sources_for(target, scene):
    if not target or target.name not in scene.objects:
        raise ValueError('请选择本场景中的人物网格或骨架')
    if target.type == 'MESH':
        result = [target]
    elif target.type == 'ARMATURE':
        result = [o for o in scene.objects if o.type == 'MESH' and o.find_armature() == target
                  and not o.hide_get() and not o.hide_render and OWNER not in o]
    else:
        raise ValueError('目标需要是网格或骨架')
    if not result:
        raise ValueError('没有找到可见的蒙皮网格；也可直接指定单个网格')
    for obj in result:
        if obj.library or obj.override_library or obj.data.library or obj.mode != 'OBJECT':
            raise ValueError(f'{obj.name}：请使用本地可编辑网格并退出编辑模式')
        if OWNER in obj:
            raise ValueError('请选择原人物网格；分离结果不能作为同一轮的输入')
    return result


def fingerprint(obj):
    h = hashlib.sha256()
    def values(items, code='f'):
        h.update(array(code, items).tobytes())
    h.update(obj.name.encode('utf8'))
    values(x for row in obj.matrix_world for x in row)
    coordinates = array('f', [0.0]) * (len(obj.data.vertices) * 3)
    obj.data.vertices.foreach_get('co', coordinates)
    h.update(coordinates.tobytes())
    values((x for p in obj.data.polygons for x in (len(p.vertices), p.material_index, *p.vertices)), 'i')
    for slot in obj.material_slots:
        mat = slot.material
        h.update((mat.name if mat else '').encode('utf8'))
        if mat and hasattr(mat, 'mmd_material'):
            h.update(mat.mmd_material.name_j.encode('utf8'))
    for group in obj.vertex_groups:
        h.update(group.name.encode('utf8'))
    # Preserve the existing byte format, but hash one buffer instead of
    # allocating two tiny arrays and invoking SHA for every influence.
    weights = bytearray()
    for v in obj.data.vertices:
        weights.extend(struct.pack('=ii', v.index, len(v.groups)))
        for g in v.groups:
            weights.extend(struct.pack('=if', g.group, g.weight))
    h.update(weights)
    rig = obj.find_armature()
    if rig:
        values(x for row in rig.matrix_world for x in row)
        for b in rig.data.bones:
            h.update(b.name.encode('utf8')); values((*b.head_local, *b.tail_local))
    return h.hexdigest()


def _space(objects):
    rigs = {o.find_armature() for o in objects} - {None}
    if len(rigs) > 1:
        raise ValueError('一次只分析同一人物骨架下的网格')
    rig = next(iter(rigs), None)
    inv = rig.matrix_world.inverted_safe() if rig else objects[0].matrix_world.inverted_safe()
    transforms = {o: inv @ o.matrix_world for o in objects}
    points = {o: [transforms[o] @ v.co for v in o.data.vertices] for o in objects}
    all_points = [p for ps in points.values() for p in ps]
    if not all_points:
        raise ValueError('网格为空')
    zmin, zmax = min(p.z for p in all_points), max(p.z for p in all_points)
    height = zmax - zmin
    if height <= 1e-8:
        raise ValueError('未识别人形模型的竖直范围')
    midx = (min(p.x for p in all_points) + max(p.x for p in all_points)) * .5
    left_sign = 1
    if rig:
        for b in rig.data.bones:
            n = _text(b.name)
            if any(w in n for w in ('leftfoot', 'footl', 'anklel', '左足首', '足首l')):
                left_sign = 1 if b.head_local.x > midx else -1
                break
    return rig, points, zmin, height, midx, left_sign


def _components(obj, coords, epsilon):
    """Join coincident seam vertices for analysis only, within each material.

    Nothing is welded in the user's mesh. Polygons remain the selection unit.
    """
    mesh = obj.data
    parent = list(range(len(mesh.polygons)))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    seen = {}
    for p in mesh.polygons:
        for v in p.vertices:
            key = (p.material_index, *(round(x / epsilon) for x in coords[v]))
            if key in seen:
                a, b = find(p.index), find(seen[key]); parent[a] = b
            else:
                seen[key] = p.index
    groups = defaultdict(list)
    for p in mesh.polygons:
        groups[find(p.index)].append(p.index)
    return list(groups.values())


def analyze(objects):
    rig, coords, bottom, height, midx, left_sign = _space(objects)
    head_cut = bottom + height * .84
    head_bones = set()
    if rig:
        head = next((b for b in rig.data.bones if _text(b.name) in ('頭', '头', 'head') or _text(b.name).endswith('head')), None)
        if head:
            head_cut = head.head_local.z + height * .012
            head_bones = {b.name for b in rig.data.bones if b == head or head in b.parent_recursive}
    proposals = []
    stats = Counter()
    for obj in objects:
        roles = []
        # Bone-name semantics are constant during this operation, not per face
        # or per vertex. No persistent geometry cache can become stale.
        head_groups = {g.index for g in obj.vertex_groups if g.name in head_bones}
        foot_groups = {g.index for g in obj.vertex_groups
                       if any(w in _text(g.name) for w in ('foot', 'toe', 'ankle', '足首', 'つま先', '脚趾'))}
        for slot in obj.material_slots:
            mat = slot.material
            name = (mat.name + ' ' + getattr(getattr(mat, 'mmd_material', None), 'name_j', '')) if mat else ''
            role = _role(name)
            roles.append(_role(obj.name) if role == 'UNKNOWN' else role)
        for faces in _components(obj, coords[obj], height * 1e-6):
            ids = set(v for i in faces for v in obj.data.polygons[i].vertices)
            points = [coords[obj][i] for i in ids]
            center = sum(points, Vector()) / len(points)
            lo, hi = min(p.z for p in points), max(p.z for p in points)
            matid = obj.data.polygons[faces[0]].material_index
            role = roles[matid] if matid < len(roles) else _role(obj.name)
            group, confidence, reason = 0, 0., '材质含义不明确，保留待识别'
            side = 4 if (center.x - midx) * left_sign >= 0 else 5
            sock_side = side + 3
            foot_weight = 0.
            head_weight = 0.
            for i in ids:
                for g in obj.data.vertices[i].groups:
                    if g.group in head_groups:
                        head_weight += g.weight / len(ids)
                    if g.group in foot_groups:
                        foot_weight += g.weight / len(ids)
            low = hi < bottom + height * .30
            if role == 'BODY':
                group, confidence, reason = 1, .8, '身体/面部材质，保留为身体；名称不能证明内部完整'
            elif role == 'HAIR':
                group, confidence, reason = 2, .9, '头发材质'
            elif role == 'SHOE':
                group, confidence, reason = side, .9, '鞋类名称与左右位置'
            elif role == 'SOCK':
                group, confidence, reason = sock_side, .9, '袜类名称与左右位置'
            elif role == 'BOTTOM':
                group, confidence, reason = 9, .9, '裤装名称'
            elif role == 'CLOTH':
                if head_weight > .75:
                    group, confidence, reason = 6, .65, '主要绑定头部的服饰，可能是发带/飘带，需核对'
                elif lo > head_cut:
                    group, confidence, reason = 6, .65, '高位服饰部件，可能是发带/发饰，需核对'
                elif low and hi > bottom + height * .20 and hi - lo > height * .15:
                    group, confidence, reason = sock_side, .6, '包覆小腿的长筒服饰，可能是袜子或靴筒，需核对'
                elif low and lo > bottom + height * .15:
                    group, confidence, reason = sock_side, .55, '小腿处服饰配件，需核对是否属于袜口'
                elif low and (lo < bottom + height * .12 or foot_weight > .15):
                    group, confidence, reason = side, .75, '服饰材质位于脚部；结合整块范围和脚骨权重'
                elif low:
                    group, confidence, reason = side, .55, '低位服饰小块，可能为鞋配件或袜子，需核对'
                elif hi < bottom + height * .66 and lo > bottom + height * .32:
                    group, confidence, reason = 9, .65, '腰部以下独立服饰，可能是裤装，需核对'
                else:
                    group, confidence, reason = 3, .85, '服饰材质；衣身、袖子及配件合并为服装'
            elif role == 'ACCESSORY':
                group, confidence, reason = 6, .85, '饰品名称'
            proposals.append(dict(obj=obj, faces=faces, vertices=ids, group=group,
                                  confidence=confidence, reason=reason, center=center, bounds=(lo,hi)))
    # Small, unnamed fittings may follow nearby garment surfaces. Never recruit
    # explicitly classified skin/hair. These additions remain review candidates.
    anchors = [(coords[p['obj']][i], p['group']) for p in proposals if p['group'] in (3, 4, 5)
               and p['confidence'] >= .7 for i in p['vertices']]
    if anchors:
        tree = KDTree(len(anchors))
        for i, (co, _) in enumerate(anchors): tree.insert(co, i)
        tree.balance()
        total_faces = sum(len(o.data.polygons) for o in objects)
        for p in proposals:
            if p['group'] or len(p['faces']) > max(32, total_faces * .02): continue
            votes = Counter()
            samples = sorted(p['vertices'])[::max(1, len(p['vertices']) // 20)]
            for i in samples:
                _, index, distance = tree.find(coords[p['obj']][i])
                if distance < height * .015: votes[anchors[index][1]] += 1
            if votes:
                group, count = votes.most_common(1)[0]
                if count >= len(samples) * .8:
                    p.update(group=group, confidence=.5, reason='小配件接近服饰表面，需预览确认')
    result = []
    details = []
    for obj in objects:
        labels = [0] * len(obj.data.polygons)
        for p in proposals:
            if p['obj'] != obj: continue
            for i in p['faces']: labels[i] = p['group']
            stats[p['group']] += len(p['faces'])
            details.append(dict(object=obj.name, group=p['group'], faces=len(p['faces']),
                                confidence=p['confidence'], reason=p['reason'], vertical_bounds=p['bounds']))
        review_faces = [i for p in proposals if p['obj'] == obj and p['confidence'] < .7 for i in p['faces']]
        result.append(dict(object=obj, fingerprint=fingerprint(obj), labels=labels, review_faces=review_faces))
    return result, dict(stats), details


def validate(sources):
    for obj, signature, labels in sources:
        if not obj or obj.mode != 'OBJECT' or fingerprint(obj) != signature or len(labels) != len(obj.data.polygons):
            raise ValueError('模型或材质/权重已变化，请退出编辑模式后重新识别')
        if any(not isinstance(x, int) or x < 0 for x in labels):
            raise ValueError('部件分组数据无效，请重新识别')


def _attribute(mesh, name, domain, values):
    old = mesh.attributes.get(name)
    if old: mesh.attributes.remove(old)
    attr = mesh.attributes.new(name, 'INT', domain)
    attr.data.foreach_set('value', values)


def _copy(obj, collection, token):
    old_actions = set(bpy.data.actions)
    clone = obj.copy(); clone.data = obj.data.copy()
    collection.objects.link(clone); clone[OWNER] = token
    clone.hide_set(False); clone.hide_viewport = False
    _animation_links(obj, clone, clone)
    for action in set(bpy.data.actions) - old_actions:
        if action.users == 0: bpy.data.actions.remove(action)
    return clone


def _animation_links(source, part, work):
    """Separate duplicates Actions; share original channels and remap self IDs."""
    for old, new in ((source, part), (source.data.shape_keys, part.data.shape_keys)):
        if not old or not old.animation_data: continue
        ad = old.animation_data; bd = new.animation_data_create()
        bd.action = ad.action
        if ad.action and ad.action_slot: bd.action_slot = ad.action_slot
        if len(ad.nla_tracks) != len(bd.nla_tracks): raise RuntimeError('分离未保留 NLA 轨道')
        for a, b in zip(ad.nla_tracks, bd.nla_tracks):
            if len(a.strips) != len(b.strips): raise RuntimeError('分离未保留 NLA 片段')
            for x, y in zip(a.strips, b.strips):
                y.action = x.action
                if x.action and x.action_slot: y.action_slot = x.action_slot
        for curve in bd.drivers:
            for var in curve.driver.variables:
                for target in var.targets:
                    if target.id in (source, work): target.id = part
                    elif target.id and target.id in (source.data.shape_keys, work.data.shape_keys):
                        target.id = part.data.shape_keys


def discard(collection):
    """Delete only objects/materials created and owned by this collection."""
    if not collection or OWNER not in collection: return
    token = collection[OWNER]
    meshes, materials = [], []
    for obj in list(collection.all_objects):
        if obj.get(OWNER) != token: continue
        if obj.type == 'MESH':
            meshes.append(obj.data)
            materials.extend(s.material for s in obj.material_slots if s.material and s.material.get(OWNER) == token)
        bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in meshes:
        if mesh.users == 0: bpy.data.meshes.remove(mesh)
    for mat in set(materials):
        if mat.users == 0: bpy.data.materials.remove(mat)
    for child in list(collection.children):
        if child.get(OWNER) == token and not child.all_objects and not child.children:
            bpy.data.collections.remove(child)
    if not collection.objects and not collection.children: bpy.data.collections.remove(collection)


def preview(scene, sources, names):
    validate(sources)
    token = uuid.uuid4().hex
    collection = bpy.data.collections.new('BA 部件识别预览'); collection[OWNER] = token
    scene.collection.children.link(collection)
    old_actions = set(bpy.data.actions)
    try:
        palette = {}
        for group, name in names.items():
            mat = bpy.data.materials.new('BA预览_' + name); mat[OWNER] = token
            mat.diffuse_color = GROUPS[group][1] if group in GROUPS else (*hsv_to_rgb((group * .61803398875) % 1, .65, .85), 1)
            palette[group] = mat
        for obj, _, labels in sources:
            clone = _copy(obj, collection, token); clone.hide_render = True
            for slot in clone.material_slots: slot.link = 'DATA'
            clone.data.materials.clear()
            indices = {group: i for i, group in enumerate(sorted(palette))}
            for group in sorted(palette): clone.data.materials.append(palette[group])
            for polygon, label in zip(clone.data.polygons, labels): polygon.material_index = indices[label]
        return collection
    except Exception:
        discard(collection); raise
    finally:
        for action in set(bpy.data.actions) - old_actions:
            if action.users == 0: bpy.data.actions.remove(action)


def _preflight_extract(sources):
    validate(sources)
    for obj, _, _ in sources:
        if len({v for p in obj.data.polygons for v in p.vertices}) != len(obj.data.vertices):
            raise ValueError(f'{obj.name}：存在不属于任何面的游离顶点，请在副本中清理后再分离')
        unsupported = [m.name for m in obj.modifiers if m.type != 'ARMATURE' and (m.show_viewport or m.show_render)]
        if unsupported:
            raise ValueError(f'{obj.name}：当前支持骨架修改器；请在另存副本中处理其他修改器：' + '、'.join(unsupported))
        if obj.data.shape_keys and not obj.data.shape_keys.use_relative:
            raise ValueError(f'{obj.name}：暂不支持绝对形态键；原模型未修改')
        if obj.data.shape_keys and 'mmd_sdef_skinning' in obj.data.shape_keys.key_blocks:
            raise ValueError(f'{obj.name}：请先在副本中解除 SDEF 实时绑定；分离后再重新绑定')
        for block in (obj, obj.data.shape_keys):
            if block and block.animation_data and any(strip.type != 'CLIP' for track in block.animation_data.nla_tracks for strip in track.strips):
                raise ValueError(f'{obj.name}：暂不支持包含合成/过渡片段的 NLA，请在副本中烘焙后再分离')


def extract(context, sources, names, selected):
    """Return a complete partition; selected groups become separate parts.

    Unselected polygons stay together as a remainder. Original objects, mesh
    data, rig, actions, visibility and physics are not modified here.
    """
    _preflight_extract(sources)
    if not selected or not any(x in selected for _, _, labels in sources for x in labels):
        raise ValueError('请勾选至少一个包含面的部件')
    token = uuid.uuid4().hex
    collection = bpy.data.collections.new('BA 分离部件'); collection[OWNER] = token
    context.scene.collection.children.link(collection)
    old_active = context.view_layer.objects.active
    old_selected = list(context.selected_objects)
    old_actions = set(bpy.data.actions)
    completed = []
    try:
        for obj, _, labels in sources:
            work = _copy(obj, collection, token)
            _attribute(work.data, FACE_ID, 'FACE', [x if x in selected else -1 for x in labels])
            _attribute(work.data, VERT_ID, 'POINT', list(range(len(work.data.vertices))))
            _attribute(work.data, SOURCE_FACE, 'FACE', list(range(len(work.data.polygons))))
            _attribute(work.data, SOURCE_LOOP, 'CORNER', list(range(len(work.data.loops))))
            groups = sorted(set(x if x in selected else -1 for x in labels), key=lambda g: (g == -1, g))
            pieces = []
            for group in groups[:-1]:
                for item in context.selected_objects: item.select_set(False)
                work.select_set(True); context.view_layer.objects.active = work
                bpy.ops.object.mode_set(mode='EDIT')
                bm = bmesh.from_edit_mesh(work.data)
                layer = bm.faces.layers.int[FACE_ID]
                for v in bm.verts: v.hide_set(False); v.select_set(False)
                for e in bm.edges: e.select_set(False)
                for f in bm.faces: f.hide_set(False); f.select_set(f[layer] == group)
                bm.select_mode = {'FACE'}; bm.select_flush_mode()
                bmesh.update_edit_mesh(work.data)
                before = set(collection.objects)
                result = bpy.ops.mesh.separate(type='SELECTED')
                bpy.ops.object.mode_set(mode='OBJECT')
                new = set(collection.objects) - before
                if result != {'FINISHED'} or len(new) != 1:
                    raise RuntimeError('部件分离未产生唯一结果，已停止并回退副本')
                part = new.pop(); part[OWNER] = token
                pieces.append((group, part))
            pieces.append((groups[-1], work))
            seen = []
            for group, part in pieces:
                part.name = f'{obj.name} · {names.get(group, "身体及未分离部分")}'
                part['baw_part_label'] = names.get(group, '身体及未分离部分')
                part['baw_part_source'] = obj.name
                part['baw_part_group_id'] = group
                if len(part.data.polygons) == 0: raise RuntimeError('分离结果为空')
                seen.extend(d.value for d in part.data.attributes[SOURCE_FACE].data)
                _animation_links(obj, part, work)
                if obj.data.has_custom_normals:
                    loop_ids = [d.value for d in part.data.attributes[SOURCE_LOOP].data]
                    part.data.normals_split_custom_set([tuple(obj.data.corner_normals[i].vector) for i in loop_ids])
                verify_piece(obj, part)
                completed.append(part)
            if sorted(seen) != list(range(len(obj.data.polygons))):
                raise RuntimeError('分离后的面出现遗漏或重复')
        # A garment spanning several source meshes remains one collection,
        # preserving incompatible shape-key systems instead of destructive joins.
        children = {}
        for part in completed:
            group = part['baw_part_group_id']
            if group not in children:
                child = bpy.data.collections.new(names.get(group, '身体及未分离部分'))
                child[OWNER] = token; collection.children.link(child); children[group] = child
            children[group].objects.link(part); collection.objects.unlink(part)
        collection['baw_parts_verified'] = True
        return collection, completed
    except Exception:
        if context.object and context.object.mode != 'OBJECT': bpy.ops.object.mode_set(mode='OBJECT')
        discard(collection); raise
    finally:
        for action in set(bpy.data.actions) - old_actions:
            if action.users == 0: bpy.data.actions.remove(action)
        for obj in context.selected_objects: obj.select_set(False)
        for obj in old_selected:
            if obj.name in context.view_layer.objects: obj.select_set(True)
        if old_active and old_active.name in context.view_layer.objects: context.view_layer.objects.active = old_active


def verify_piece(source, part):
    """Verify provenance against all shape coordinates, UVs and skin weights."""
    ids = [v.value for v in part.data.attributes[VERT_ID].data]
    for v, original in zip(part.data.vertices, ids):
        ref = source.data.vertices[original]
        if (v.co - ref.co).length > 1e-6: raise RuntimeError('分离改变了静置顶点')
        a = {part.vertex_groups[g.group].name: g.weight for g in v.groups}
        b = {source.vertex_groups[g.group].name: g.weight for g in ref.groups}
        if a != b: raise RuntimeError('分离改变了骨骼权重')
    if source.data.shape_keys:
        old, new = source.data.shape_keys, part.data.shape_keys
        if not new or list(old.key_blocks.keys()) != list(new.key_blocks.keys()):
            raise RuntimeError('分离未保留全部形态键')
        for key in old.key_blocks:
            copy = new.key_blocks[key.name]
            if copy.relative_key.name != key.relative_key.name: raise RuntimeError('形态键相对关系改变')
            if any((copy.data[i].co - key.data[j].co).length > 1e-6 for i, j in enumerate(ids)):
                raise RuntimeError('形态键坐标改变')
        ad, bd = old.animation_data, new.animation_data
        if (ad.action if ad else None) != (bd.action if bd else None): raise RuntimeError('形态键动画未保留')
        if len(ad.drivers if ad else []) != len(bd.drivers if bd else []): raise RuntimeError('形态键驱动未保留')
    loops = [v.value for v in part.data.attributes[SOURCE_LOOP].data]
    for uv in source.data.uv_layers:
        copy = part.data.uv_layers.get(uv.name)
        if not copy or any((copy.uv[i].vector - uv.uv[j].vector).length > 1e-6 for i, j in enumerate(loops)):
            raise RuntimeError('分离改变了 UV')
    if source.data.has_custom_normals:
        # Blender encodes custom normals in the new loop spaces with finite
        # precision. Bound that round-trip error instead of requiring bit identity.
        normal_error = max(((part.data.corner_normals[i].vector - source.data.corner_normals[j].vector).length for i, j in enumerate(loops)), default=0)
        part['baw_part_normal_max_error'] = normal_error
        if normal_error > 1e-3: raise RuntimeError(f'自定义法线误差超出允许范围：{normal_error:.6f}')
    faces = [v.value for v in part.data.attributes[SOURCE_FACE].data]
    for polygon, index in zip(part.data.polygons, faces):
        original = source.data.polygons[index]
        mat = part.material_slots[polygon.material_index].material if part.material_slots else None
        old = source.material_slots[original.material_index].material if source.material_slots else None
        if mat != old: raise RuntimeError('分离改变了材质分配')
    if source.find_armature() != part.find_armature(): raise RuntimeError('分离改变了骨架绑定')
