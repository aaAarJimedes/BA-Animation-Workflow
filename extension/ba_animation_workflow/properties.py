import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty

from .constants import CAMERA_RIG_ITEMS, CLEANUP_PROFILE_ITEMS, SHOT_ITEMS


WORKSPACE_MODE_ITEMS = (
    ("AUTO", "全自动", "只显示模型、创作描述、运行状态和必要设置"),
    ("MANUAL", "分步制作", "按工程、动作、修正、镜头和交付阶段逐步工作"),
)

MANUAL_STAGE_ITEMS = (
    ("PROJECT", "1 · 工程准备", "创建项目目录和安全场景集合"),
    ("MOTION", "2 · AI 动作", "生成动作并输出到用户角色"),
    ("CLEANUP", "3 · 动作修正", "非破坏清理动作并建立人工修正层"),
    ("SHOT", "4 · 镜头灯光", "创建角色镜头、切镜标记与三点灯光"),
    ("DELIVERY", "5 · 预览交付", "准备预览、运行检查并按所有权安全清理"),
    ("LEGACY", "传统 BVH", "使用 BlendCap Motion Bridge 处理传统视频动捕"),
)


def _apply_cleanup_profile(self, _context):
    strength, passes, tolerance = {
        "LIGHT": (0.08, 1, 0.002),
        "STANDARD": (0.20, 1, 0.005),
        "STRONG": (0.35, 2, 0.012),
    }[self.cleanup_profile]
    self.smooth_strength = strength
    self.smooth_passes = passes
    self.simplify_tolerance = tolerance


class BAW_PG_settings(bpy.types.PropertyGroup):
    workspace_mode: EnumProperty(
        name="工作模式",
        items=WORKSPACE_MODE_ITEMS,
        default="AUTO",
    )
    manual_stage: EnumProperty(
        name="当前阶段",
        items=MANUAL_STAGE_ITEMS,
        default="PROJECT",
    )
    show_cleanup_parameters: BoolProperty(name="显示清理参数", default=False)
    show_delivery_maintenance: BoolProperty(name="显示安全清理", default=False)
    show_diagnostics: BoolProperty(name="显示组件诊断", default=False)
    project_root: StringProperty(
        name="项目根目录",
        description="本工具只会在这里创建固定目录并清理自身缓存",
        subtype="DIR_PATH",
    )
    shot_type: EnumProperty(
        name="镜头景别",
        items=SHOT_ITEMS,
        default="MEDIUM",
    )
    camera_rig_mode: EnumProperty(
        name="专业相机 Rig",
        items=CAMERA_RIG_ITEMS,
        default="DOLLY",
    )
    light_power: FloatProperty(
        name="主光强度",
        description="自动三点光中主光的基础功率",
        default=800.0,
        min=10.0,
        max=100000.0,
        soft_max=5000.0,
    )
    simplify_tolerance: FloatProperty(
        name="简化容差",
        description="允许曲线偏离原始值的最大幅度；先从 0.003 到 0.01 试起",
        default=0.005,
        min=0.0,
        max=1.0,
        precision=4,
    )
    smooth_strength: FloatProperty(
        name="平滑强度",
        description="邻帧平均的混合强度；0 表示不平滑",
        default=0.2,
        min=0.0,
        max=1.0,
        subtype="FACTOR",
    )
    smooth_passes: IntProperty(
        name="平滑次数",
        description="次数越高越稳，但会削弱快速动作",
        default=1,
        min=0,
        max=5,
    )
    cleanup_profile: EnumProperty(
        name="清理强度",
        items=CLEANUP_PROFILE_ITEMS,
        default="STANDARD",
        update=_apply_cleanup_profile,
    )
    last_clean_summary: StringProperty(default="尚未清理动作", options={"HIDDEN"})
    last_audit_summary: StringProperty(default="尚未运行交付检查", options={"HIDDEN"})
    last_workflow_summary: StringProperty(default="场景尚未初始化", options={"HIDDEN"})


CLASSES = (BAW_PG_settings,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.baw_settings = PointerProperty(type=BAW_PG_settings)


def unregister():
    if hasattr(bpy.types.Scene, "baw_settings"):
        del bpy.types.Scene.baw_settings
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
