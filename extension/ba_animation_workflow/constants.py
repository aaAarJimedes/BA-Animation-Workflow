ADDON_VERSION = (0, 11, 0)

TOOL_ID = "ba_animation_workflow"
TOOL_NAME = "BA Animation Workflow"
OWNER_KEY = "baw_owner"
OWNER_VALUE = TOOL_ID
ROLE_KEY = "baw_role"
SCENE_ID_KEY = "baw_scene_id"
WORKSPACE_SCHEMA = 1
CACHE_MARKER = ".baw_cache_owner"

ROOT_COLLECTION = "BAW_PIPELINE"
COLLECTIONS = (
    "BAW_00_REFERENCE",
    "BAW_10_CHARACTER",
    "BAW_20_MOCAP_RAW",
    "BAW_30_MOTION_CLEAN",
    "BAW_40_STAGE",
    "BAW_50_LIGHTS",
    "BAW_60_CAMERAS",
    "BAW_90_OUTPUT",
)

PROJECT_FOLDERS = (
    "00_reference",
    "10_models",
    "20_mocap_raw",
    "30_motion_clean",
    "40_audio",
    "50_cache/baw_generated",
    "60_renders_preview",
    "70_renders_final",
    "90_exports",
)

WORKSPACE_MARKER = ".baw_workspace"

EXTERNAL_ADDONS = {
    "BlendCap": ("blendcap",),
    "MMD Tools": ("mmd_tools", "blender_mmd_tools"),
    "BlendCap Motion Bridge": ("blendcap_motion_bridge",),
    "Proscenium": ("proscenium_blender",),
    "Proscenium Motion Bridge": ("proscenium_motion_bridge", "ba_motion_bridge"),
    "Add Camera Rigs": ("add_camera_rigs",),
}

SHOT_ITEMS = (
    ("FULL", "全身", "完整角色与少量环境"),
    ("MEDIUM", "中景", "腰部以上，适合对白与表演"),
    ("CLOSE", "近景", "突出面部与表情"),
    ("ACTION", "动作镜头", "带侧向透视的动态构图"),
)

CAMERA_RIG_ITEMS = (
    ("DOLLY", "Dolly", "适合推拉、横移和跟拍"),
    ("CRANE", "Crane", "适合升降和弧线运动"),
    ("2D", "2D Rig", "适合稳定构图、摇摄与变焦"),
)

CLEANUP_PROFILE_ITEMS = (
    ("LIGHT", "轻度", "尽量保留动作细节，适合 AI 生成动作"),
    ("STANDARD", "标准", "平衡稳定与关键帧数量，推荐新手使用"),
    ("STRONG", "强力", "更明显地平滑位移与欧拉曲线，适合抖动较大的视频动捕"),
)
