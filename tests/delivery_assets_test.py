"""Run with Blender --background --factory-startup --python this.py -- OUT_DIR.

Exercises real media, missing dependencies, rollback, append provenance, and a
save/reopen round trip. Creates fixtures only in the explicit output directory.
"""
import importlib.util
import json
import math
from pathlib import Path
import sys
import wave

import bpy


out = Path(sys.argv[sys.argv.index('--') + 1]).resolve()
allowed = Path('D:/Agent Workspaces/Agent Temp/BA_Animation_Workflow/testing').resolve()
assert out == allowed or allowed in out.parents, 'Fixture output must stay under the task testing directory'
out.mkdir(parents=True, exist_ok=True)
module_path = Path(__file__).resolve().parents[1] / 'extension/ba_animation_workflow/delivery_assets.py'
spec = importlib.util.spec_from_file_location('baw_delivery_assets_tested', module_path)
assets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assets)

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.fps, scene.render.fps_base = 24, 1.001
scene.frame_start, scene.frame_end = -30, 778
bpy.ops.mesh.primitive_cube_add()
obj = bpy.context.object
obj.location = (1, 2, 3)
obj.keyframe_insert('location', frame=-30)
obj.location = (2, 3, 4)
obj.keyframe_insert('location', frame=778)
action = obj.animation_data.action
mesh = obj.data
scene.frame_set(-30)


def state():
    return (scene.render.fps, scene.render.fps_base, scene.frame_start, scene.frame_end,
            scene.frame_current, tuple(obj.location), mesh.as_pointer(), len(mesh.vertices),
            obj.animation_data.action.as_pointer(), tuple(action.frame_range), bpy.data.filepath)


original_state = state()
png = out / 'texture.png'
image = bpy.data.images.new('fixture_generated', 4, 4)
image.generated_color = (.2, .5, .7, 1)
image.save_render(str(png))
bpy.data.images.remove(image)
image = bpy.data.images.load(str(png), check_existing=False)
image.name = 'unpacked_texture'
image.use_fake_user = True
packed = bpy.data.images.load(str(png), check_existing=False)
packed.name = 'already_packed_old_path'
packed.use_fake_user = True
packed.pack()
packed.filepath = str(out / 'does_not_exist.png')
wav = out / 'tone.wav'
with wave.open(str(wav), 'wb') as handle:
    handle.setnchannels(1)
    handle.setsampwidth(2)
    handle.setframerate(48000)
    handle.writeframes(bytes(9600))
sound = bpy.data.sounds.load(str(wav), check_existing=False)
sound.use_fake_user = True
font_path = Path('C:/Windows/Fonts/arial.ttf')
font = bpy.data.fonts.load(str(font_path)) if font_path.exists() else None
if font:
    font.use_fake_user = True

initial = assets.inspect_assets()
assert state() == original_state
assert not initial['summary']['MISSING'], initial
assert initial['summary']['PACKABLE'] >= 2
assert any(a['name'] == packed.name and a['status'] == 'PACKED' for a in initial['assets'])

# Missing input prevents all packing, including valid inputs that come first.
missing = bpy.data.images.load(str(png), check_existing=False)
missing.filepath = str(out / 'missing.png')
try:
    assets.pack_assets()
    raise AssertionError('Missing dependency should stop before mutation')
except assets.AssetPackError as exc:
    assert exc.report['summary']['MISSING'] > 0
assert not image.packed_file and not sound.packed_file
assert packed.packed_file
assert state() == original_state
bpy.data.images.remove(missing)

# A runtime error after one successful pack must revert only this invocation.
real_pack = assets._pack_one
calls = []


def injected_failure(block):
    calls.append(block.name)
    if len(calls) == 2:
        real_pack(block)  # Even a partially successful second operation is undone.
        raise RuntimeError('injected pack failure')
    real_pack(block)


assets._pack_one = injected_failure
try:
    assets.pack_assets()
    raise AssertionError('Injected failure should abort')
except assets.AssetPackError as exc:
    assert exc.report['operation']['status'] == 'ROLLED_BACK', exc.report
finally:
    assets._pack_one = real_pack
assert not image.packed_file and not sound.packed_file
assert packed.packed_file
assert image.filepath == str(png)
assert state() == original_state

success = assets.pack_assets()
assert success['operation']['packed_count'] >= 2
assert success['all_detected_dependencies_embedded'], success
assert image.packed_file and sound.packed_file and (not font or font.packed_file)
assert assets.pack_assets()['operation']['packed_count'] == 0
assert state() == original_state

# Sequence entry can exist while delivery is still not self-contained.
sequence = bpy.data.images.load(str(png), check_existing=False)
sequence.source = 'SEQUENCE'
report = assets.inspect_assets()
assert any(a['kind'] == 'IMAGE_SEQUENCE' and a['status'] == 'EXTERNAL' for a in report['assets'])
assert not report['all_detected_dependencies_embedded']
bpy.data.images.remove(sequence)

# Generated parameters survive saving; painted pixels need explicit review.
generated = bpy.data.images.new('generated_parameters', 4, 4)
generated.generated_color = (.1, .4, .3, 1)
generated.use_fake_user = True
assert not generated.is_dirty
generated_pixels = list(generated.pixels)
assert any(a['name'] == generated.name and a['status'] == 'INTERNAL' for a in assets.inspect_assets()['assets'])
painted = bpy.data.images.new('painted_generated', 4, 4)
painted.pixels[0] = .75
assert painted.is_dirty
assert any(a['name'] == painted.name and a['status'] == 'REVIEW' for a in assets.inspect_assets()['assets'])
bpy.data.images.remove(painted)

# Per-bake paths override the modifier default. PACKED target alone proves no bake.
group = bpy.data.node_groups.new('delivery_bake_fixture', 'GeometryNodeTree')
group.interface.new_socket(name='Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
group.interface.new_socket(name='Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
group.nodes.new('NodeGroupOutput')
group.nodes.new('GeometryNodeBake')
modifier = obj.modifiers.new('delivery_bake_fixture', 'NODES')
modifier.node_group = group
bpy.context.view_layer.update()
assert len(modifier.bakes) == 1
bake = modifier.bakes[0]
assert any(a['kind'] == 'GEOMETRY_NODES_CACHE' and a['status'] == 'REVIEW' for a in assets.inspect_assets()['assets'])
bake.bake_target = 'DISK'
bake.use_custom_path = True
bake.directory = str(out / 'missing_custom_bake')
assert any(a['kind'] == 'GEOMETRY_NODES_CACHE' and a['status'] == 'MISSING' and a['absolute_path'] == bake.directory for a in assets.inspect_assets()['assets'])
obj.modifiers.remove(modifier)
bpy.data.node_groups.remove(group)

# A real linked library is a dependency; local appended origins are not.
lib_path = out / 'library_fixture.blend'
lib_mesh = bpy.data.meshes.new('library_fixture_mesh')
lib_obj = bpy.data.objects.new('library_fixture_object', lib_mesh)
bpy.data.libraries.write(str(lib_path), {lib_obj})
bpy.data.objects.remove(lib_obj)
bpy.data.meshes.remove(lib_mesh)
with bpy.data.libraries.load(str(lib_path), link=False, reuse_local_id=True) as (src, dst):
    dst.objects = ['library_fixture_object']
appended = dst.objects[0]
assert appended.library is None
weak_blocks = [b for b in (appended, appended.data) if b.library_weak_reference]
assert weak_blocks, 'Fixture must actually contain a LibraryWeakReference'
old_name = out / 'library_fixture.moved.blend'
lib_path.replace(old_name)
report = assets.inspect_assets()
assert report['historical_sources'], report
assert report['summary']['MISSING'] == 0, report
assert report['all_detected_dependencies_embedded'], report
old_name.replace(lib_path)
with bpy.data.libraries.load(str(lib_path), link=True) as (src, dst):
    dst.objects = ['library_fixture_object']
linked = dst.objects[0]
linked_library = linked.library
assert any(a['kind'] == 'LIBRARY' and a['status'] == 'EXTERNAL' for a in assets.inspect_assets()['assets'])
lib_path.replace(old_name)
report = assets.inspect_assets()
assert any(a['kind'] == 'LIBRARY' and a['status'] == 'MISSING' for a in report['assets']), report
old_name.replace(lib_path)
bpy.data.libraries.remove(linked_library)

# Preserve report after round trip and verify relocated media remains packed.
assets.register()
assert bpy.ops.baw.inspect_assets() == {'FINISHED'}
assert assets.REPORT_NAME in bpy.data.texts
assets.unregister()
assert state() == original_state
packed_path = out / 'packed_fixture.blend'
bpy.ops.wm.save_as_mainfile(filepath=str(packed_path), check_existing=False)
png.rename(out / 'texture.moved.png')
wav.rename(out / 'tone.moved.wav')
bpy.ops.wm.open_mainfile(filepath=str(packed_path))
reopened = assets.inspect_assets()
assert reopened['all_detected_dependencies_embedded'], reopened
assert bpy.data.images['unpacked_texture'].packed_file
assert any(s.packed_file for s in bpy.data.sounds)
assert all(math.isclose(a, b, abs_tol=1e-6) for a, b in zip(generated_pixels, bpy.data.images['generated_parameters'].pixels))
assert bpy.context.scene.render.fps == 24
assert math.isclose(bpy.context.scene.render.fps_base, 1.001, abs_tol=1e-6)
assert bpy.context.scene.frame_start == original_state[2]
assert bpy.context.scene.frame_current == -30
assert tuple(bpy.data.objects['Cube'].animation_data.action.frame_range) == (-30.0, 778.0)
(out / 'texture.moved.png').rename(png)
(out / 'tone.moved.wav').rename(wav)
(out / 'delivery_assets_result.json').write_text(json.dumps(dict(
    result='PASS', blender=bpy.app.version_string,
    checks=['missing-preflight-no-mutation', 'runtime-failure-rollback', 'keep-existing-packs',
            'image-sound-font-pack', 'idempotent', 'sequence-manual', 'weak-reference-not-dependency',
            'real-missing-library', 'registered-operator-report', 'save-reopen-packed-media',
            'generated-parameter-pixels-roundtrip', 'painted-generated-review', 'geometry-node-per-bake-paths',
            'animation-mesh-fps-pre-roll-preserved'], report=reopened), ensure_ascii=False, indent=2), encoding='utf-8')
print('DELIVERY_ASSETS_TEST_PASS', str(out))
