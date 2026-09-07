_needs_reload = "bpy" in locals()

import bpy

from . import auto_director, operators, panels, properties

if _needs_reload:
    import importlib

    properties = importlib.reload(properties)
    auto_director = importlib.reload(auto_director)
    operators = importlib.reload(operators)
    panels = importlib.reload(panels)


def register():
    properties.register()
    auto_director.register()
    operators.register()
    panels.register()


def unregister():
    panels.unregister()
    operators.unregister()
    auto_director.unregister()
    properties.unregister()
