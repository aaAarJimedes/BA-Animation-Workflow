"""State transitions, live dependency status, timing and panel RNA contracts."""
import sys, json, hashlib
from array import array
from pathlib import Path
from types import SimpleNamespace
import bpy
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'extension'))
import ba_animation_workflow as ba
from ba_animation_workflow import parts, parts_ui, panels, utils, physics_ui, render_plan, finishing
ba.register()
s = bpy.context.scene
s.render.fps = 24; s.render.fps_base = 1.001
s.frame_start = -30; s.frame_end = 778
timing = (s.render.fps, s.render.fps_base, s.frame_start, s.frame_end)
assert bpy.ops.baw.prepare_preview() == {'FINISHED'}
assert (s.render.fps, s.render.fps_base, s.frame_start, s.frame_end) == timing
obj = bpy.context.object
mat = bpy.data.materials.new('jacket'); obj.data.materials.append(mat)
group = obj.vertex_groups.new(name='foot'); group.add([0, 1], .37, 'REPLACE')
# Existing 0.13 saved analysis fingerprints remain valid after upgrading.
h = hashlib.sha256()
def values(items, code='f'): h.update(array(code, items).tobytes())
h.update(obj.name.encode()); values(x for row in obj.matrix_world for x in row)
values(x for v in obj.data.vertices for x in v.co)
values((x for p in obj.data.polygons for x in (len(p.vertices), p.material_index, *p.vertices)), 'i')
for slot in obj.material_slots: h.update(slot.material.name.encode())
for g in obj.vertex_groups: h.update(g.name.encode())
for v in obj.data.vertices:
    values((v.index, len(v.groups)), 'i')
    for g in v.groups: values((g.group,), 'i'); values((g.weight,))
assert parts.fingerprint(obj) == h.hexdigest()
p = s.baw_parts; p.target = obj
assert bpy.ops.baw.parts_analyze() == {'FINISHED'}
old = p.sources[0].labels
bpy.ops.mesh.primitive_cube_add(); other = bpy.context.object
p.target = other
try: parts_ui.source_data(p)
except ValueError: pass
else: raise AssertionError('Old plan accepted for changed target')
assert p.sources[0].labels == old
p.target = obj
p.active = 100
try: parts_ui.active_group(p)
except ValueError: pass
else: raise AssertionError('Invalid selection accepted')
p.active = 3
p.sources[0].review_faces = '[0,1]'
parts_ui.recount(p); assert sum(g.review for g in p.groups) == 2
p.sources[0].review_faces = '[1]'
parts_ui.recount(p); assert sum(g.review for g in p.groups) == 1
p.sources[0].review_faces = '[]'
parts_ui.recount(p); assert sum(g.review for g in p.groups) == 0
# Validate UI property/operator names in real Blender, including collapsed
# panels' draw paths. This does not claim pixel-level GUI validation.
class Layout:
    def __init__(self): self.calls = []
    def prop(self, data, name, **kwargs):
        assert hasattr(data, name), (type(data), name)
        self.calls.append(('prop', name))
    def operator(self, name, **kwargs):
        namespace, op = name.split('.')
        getattr(getattr(bpy.ops, namespace), op).get_rna_type()
        self.calls.append(('operator', name)); return SimpleNamespace()
    def __getattr__(self, name):
        return lambda *args, **kwargs: self
layout = Layout(); panel = SimpleNamespace(layout=layout)
for cls in (panels.BAW_PT_main, panels.BAW_PT_workflow, parts_ui.BAW_PT_parts,
            physics_ui.BAW_PT_physics, render_plan.BAW_PT_delivery, finishing.BAW_PT_finishing):
    cls.draw(panel, bpy.context)
for stage in ('PROJECT', 'MOTION', 'CLEANUP', 'SHOT', 'DELIVERY', 'LEGACY'):
    s.baw_settings.workspace_mode = 'MANUAL'; s.baw_settings.manual_stage = stage
    panels.BAW_PT_workflow.draw(panel, bpy.context)
s.baw_settings.show_diagnostics = True; panels.BAW_PT_main.draw(panel, bpy.context)
for text in ('中文提示 English', '第一行\n第二行', 'longtext' * 20):
    assert ''.join(panels._wrap_lines(text, 18)).replace(' ', '') == text.replace('\n', '').replace(' ', '')
assert utils.external_addon_status() == {n:utils.module_enabled(t) for n,t in utils.EXTERNAL_ADDONS.items()}
ba.unregister(); ba.register()
print('WORKBENCH_OPTIMIZATION_OK', len(layout.calls))
