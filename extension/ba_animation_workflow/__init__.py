_needs_reload = "bpy" in locals()

import bpy

from . import auto_director, operators, panels, properties, finishing

if _needs_reload:
    import importlib

    for name in ['constants', 'utils', 'clip_plan', 'foot_contact', 'seam_smoothing', 'split_seam', 'properties', 'auto_director', 'operators', 'panels', 'finishing']:
        importlib.reload(importlib.import_module("." + name, __package__))


def register():
    properties.register()
    auto_director.register()
    operators.register()
    panels.register()
    finishing.register()


def unregister():
    finishing.unregister()
    panels.unregister()
    operators.unregister()
    auto_director.unregister()
    properties.unregister()
