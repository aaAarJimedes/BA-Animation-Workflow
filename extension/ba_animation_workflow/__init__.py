_needs_reload = "bpy" in locals()

import bpy

from . import auto_director, operators, panels, properties, finishing, physics, physics_ui, delivery_assets, render_plan, parts, parts_ui

if _needs_reload:
    import importlib

    for name in ['constants', 'utils', 'clip_plan', 'foot_contact', 'seam_smoothing', 'split_seam', 'properties', 'auto_director', 'operators', 'panels', 'finishing', 'physics', 'physics_ui', 'delivery_assets', 'render_plan', 'parts', 'parts_ui']:
        importlib.reload(importlib.import_module("." + name, __package__))


def register():
    properties.register()
    auto_director.register()
    operators.register()
    panels.register()
    finishing.register()
    physics_ui.register()
    delivery_assets.register()
    render_plan.register()
    parts_ui.register()


def unregister():
    parts_ui.unregister()
    render_plan.unregister()
    delivery_assets.unregister()
    physics_ui.unregister()
    finishing.unregister()
    panels.unregister()
    operators.unregister()
    auto_director.unregister()
    properties.unregister()
