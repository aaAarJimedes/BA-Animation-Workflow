from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import sys

import bpy


if not bpy.app.background:
    raise RuntimeError("Panel layout test refuses to run in Blender UI")
if os.environ.get("BAM_PANEL_TEST_ALLOW") != "isolated-factory-test":
    raise RuntimeError("Set BAM_PANEL_TEST_ALLOW=isolated-factory-test explicitly")

WORKSPACE = Path(r"D:\Agent Workspaces\Agent Tools\BA_Animation_Workflow")
sys.path.insert(0, os.environ.get("BAM_BRIDGE_IMPORT_ROOT", str(WORKSPACE / "extension")))
module_name = os.environ.get("BAM_BRIDGE_MODULE", "ba_motion_bridge")
addon = importlib.import_module(module_name)
panels = importlib.import_module(module_name + ".panels")
addon.register()


def check(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


class LayoutProbe:
    def __init__(self, events):
        self.events = events
        self.enabled = True
        self.alert = False
        self.scale_y = 1.0

    def box(self):
        return LayoutProbe(self.events)

    def row(self, **_kwargs):
        return LayoutProbe(self.events)

    def column(self, **_kwargs):
        return LayoutProbe(self.events)

    def label(self, *, text="", icon="NONE", **_kwargs):
        self.events.append(("label", text, icon))

    def prop(self, data, name, **kwargs):
        self.events.append(("prop", name, kwargs.get("text")))

    def operator(self, identifier, *, text="", icon="NONE", **_kwargs):
        self.events.append(("operator", identifier, text, icon))
        return SimpleNamespace()

    def progress(self, *, factor=0.0, type="BAR", text="", **_kwargs):
        self.events.append(("progress", factor, type, text))


settings = bpy.context.scene.ba_motion_bridge_settings
settings.last_output_action = "ACT_伊落玛丽_Proscenium_Extremely_Long_Output_Action_Name_MMD"
settings.status_message = "这是一个用于验证窄面板会自动换行而不是要求用户横向拉宽的长状态说明。"
settings.status_level = "INFO"
settings.expected_count = 24
settings.matched_count = 24
settings.mapping_valid = True
settings.target_profile = "MMD"

events = []
panel = SimpleNamespace(layout=LayoutProbe(events))
panels.BAM_PT_proscenium_motion_bridge.draw(panel, bpy.context)
operator_texts = [event[2] for event in events if event[0] == "operator"]
labels = [event[1] for event in events if event[0] == "label"]
props = [event[1] for event in events if event[0] == "prop"]
check("重新激活并预热物理" in operator_texts, "activation button is still ambiguous")
check("只复查当前映射" in operator_texts, "mapping recheck button lacks purpose")
check(sum("ACT_" in label or "MMD" in label for label in labels) >= 2, "long Action name was not wrapped")
check("不删除输出Action" in "".join(labels).replace(" ", ""), "cleanup/recovery safety note missing")
check("use_end_effector_guard" in props, "end-effector guard is missing from output settings")
check("end_effector_guard_strength" in props, "end-effector guard strength is missing")
check("1.00为标准" in "".join(labels).replace(" ", ""), "end-effector guard strength explanation is missing")

settings.progress_active = True
settings.progress_value = 0.42
settings.progress_message = "重定向：烘焙动作帧 42/100"
progress_events = []
panel.layout = LayoutProbe(progress_events)
panels.BAM_PT_proscenium_motion_bridge.draw(panel, bpy.context)
bars = [event for event in progress_events if event[0] == "progress"]
check(len(bars) == 1, "active operation did not draw exactly one progress bar")
check(abs(bars[0][1] - 0.42) < 1e-6, "progress bar factor is incorrect")
check("42/100" in bars[0][3], "progress bar message is missing")

print(
    "PMB_PANEL_LAYOUT_TEST="
    + json.dumps(
        {
            "status": "PASS",
            "operator_buttons": operator_texts,
            "wrapped_action_lines": sum("ACT_" in label or "MMD" in label for label in labels),
            "progress_factor": bars[0][1],
            "end_effector_guard": "use_end_effector_guard" in props,
            "end_effector_guard_strength": "end_effector_guard_strength" in props,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
)

addon.unregister()
