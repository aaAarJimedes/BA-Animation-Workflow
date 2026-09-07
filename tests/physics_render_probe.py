"""Render two review frames without saving changes to the project."""
import bpy, sys
from pathlib import Path
source, out = map(Path, sys.argv[sys.argv.index('--')+1:])
out.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(source),load_ui=False,use_scripts=False)
s=bpy.context.scene
assert not s.rigidbody_world.enabled
s.render.resolution_percentage=50
s.render.image_settings.file_format='PNG'
s.render.image_settings.color_mode='RGB'
for f in (0,399):
    s.frame_set(f)
    s.render.filepath=str(out/f'physics_{f:04d}.png')
    bpy.ops.render.render(write_still=True)
print('PHYSICS_RENDER_PASS',flush=True)
