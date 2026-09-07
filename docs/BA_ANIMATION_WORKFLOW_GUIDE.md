# BA Animation Workflow 一站式使用指南

适用版本：Blender 5.1.2、BA Animation Workflow 0.9.0、Proscenium Motion Bridge 0.9.1、BlendCap Motion Bridge 0.4.0、Proscenium Hosted 0.4.0、BlendCap 1.0.5。

## 先理解两个标签

这套工作流使用一个渐进式主面板，只显示当前模式和当前阶段需要的操作：

- `N → Proscenium`：完成自然语言动作的生成、预览、接受和 MMD 输出。预览满意时，可在同一标签直接点击“接受并输出到 MMD”；不必先 Accept，再切到另一个面板重定向。
- `N → BA 动画`：顶部切换“全自动 / 分步制作”。全自动模式默认只有一个主运行键；分步模式通过阶段下拉显示当前工具。诊断、高级参数和安全清理按需展开。

统一界面不等于把代码合成一个插件。以下三个技术包仍可独立安装、启用、升级和排错：

| 技术包 | 版本 | 职责 |
|---|---:|---|
| BA Animation Workflow | 0.9.0 | 文本块主索引、真实源提示词优先的双重校验、覆盖前同源验证、误替换 NLA 自动恢复、稳定 Clip ID、同文本同模型动作自动接管、孤立源动作恢复、旧模型动作逐段或批量导入新模型、已有动作重新映射替换、单段总帧数、当前帧放置、上一段 Action 与负滚动区的 NLA 保留、根运动父子链无重复位移、身体骨骼首帧短过渡、辅助骨状态保护、分阶段工程、可选镜头灯光与交付工具 |
| Proscenium Motion Bridge | 0.9.1 | 使用自有引擎完成官方 `kimodo-soma-rp` 到 MMD/Auto-Rig Pro 的检查、映射、目标布置动作空间、可调肢端防穿模、负帧物理预滚动、多角色恢复与重定向 |
| BlendCap Motion Bridge | 0.4.0 | 传统 BlendCap/BVH 动捕到 MMD 的自动映射、安全重定向、负帧预滚动、表情与 VMD 后处理 |

Proscenium Hosted 仍是独立的第三方生成插件。Proscenium Motion Bridge 只把自己的单一顺序面板注入 `Proscenium` 标签，不修改 Proscenium 的生成逻辑；BA Animation Workflow 通过公开操作符和 Scene 状态连接各组件，不把它们硬打包在一起。

## 第一次使用

1. 启动 `D:\softwares\Blender Foundation\Blender 5.1\blender.exe`。当前正式配置锁定 Blender 5.1.2，不要误用 Steam Blender 5.2。
2. 打开角色工程的副本。不要直接在唯一原件上测试新动作。
3. 用 MMD Tools 导入角色，确认选中的目标是人体主 Armature，而不是武器、光环或服装辅助骨架。
4. 打开 `N → BA 动画`，检查顶部“核心组件”状态。AI 主线只需要 MMD Tools、Proscenium 和 Proscenium Motion Bridge；BlendCap 仅供传统 BVH 视频动捕路线使用。
5. 切换到“分步制作”，在“1 · 工程准备”选择专用项目根目录，然后点击唯一的“初始化工程目录与场景”。

初始化只创建本工具的固定目录、集合和所有权标记。它不会接管同名用户对象，也不会自动删除模型、贴图、音频、动作或 `.blend` 文件。

## 最短 AI 动作路径

### 1. 导入官方骨架

切到 `N → Proscenium`：

1. 连接服务并刷新模型列表；Blender 重启后通常需要重新连接。
2. 选择官方 `kimodo-soma-rp` 模型。
3. 导入 Canonical Skeleton，确认场景里出现带官方模型标记的 30 骨 Armature。

不要把 MMD 角色直接冒充官方骨架，也不要把官方 SOMA 骨架交给 BlendCap Motion Bridge 的传统 Detect。SOMA 的 `LeftLeg` 是大腿、`LeftShin` 是小腿；传统 BVH 常用的是另一套命名语义。

### 2. 生成与预览

在 Proscenium Timeline 创建 Prompt Block，把动作写成可检查的短段落。新手提示词至少写清：

- 动作顺序与总时长；
- 左右手、左右脚和身体朝向；
- 速度、停顿、重心变化；
- 起始与结束姿势；
- 是否需要完整 Root 位移或原地循环。

生成后先在官方骨架上播放预览。检查整体节奏、脚步次数、朝向、手部路径和结束平衡；此时修提示词通常比重定向后逐帧大修更省时。

### 3. 在 Proscenium 内直接输出到 MMD

同一 `Proscenium` 标签下会出现唯一的 `Proscenium Motion Bridge` 面板：

1. “源骨架”选择官方 `kimodo-soma-rp`；“MMD 目标”选择角色人体主 Armature。
2. 选择输出方式：

   - `完整位移`：传递身体旋转和 Root 位移，预期主链 `24/24`；
   - `原地动作`：不传 Root 位移，预期主链 `22/22`。

3. 保持“跟随 Proscenium In-place”时，Bridge 会按当前预览设置自动选择位移模式；需要固定结果时可关闭后手动选择。
4. 点击“自动识别并检查”。确认没有关键骨缺失、非等比缩放、重复旋转目标或位置轴冲突。
5. 预览满意时点击“接受并输出到 MMD”。按钮会先调用 Proscenium Accept，再检查映射并输出独立 MMD Action。

如果动作已经 Accept，按钮会显示“一键输出到 MMD”，并直接读取活动 Action 或已接受的 `Proscenium: Motion` NLA。生成进行中时输出会锁定，避免读到半成品状态。

成功后：

- 目标骨架使用新的 `ACT_<角色>_<动作>_MMD` Action；
- Action 带 Fake User 与 Bridge 所有权标记，不覆盖原目标关键帧；
- `BA 动画 → 分步制作 → 2 · AI 动作` 显示上次输出，可点击“重新激活并预热物理”；
- 原目标 Action、Action Slot、NLA 状态和腿链约束都有可恢复快照。

如果 Accept 成功而后续重定向失败，已接受的 Proscenium 动作仍会保留。按界面的关键缺失或缩放提示修正目标后，再点“一键输出到 MMD”，无需重新消耗一次生成。

## 分阶段完成动画

输出 MMD Action 后切回 `N → BA 动画 → 分步制作`，用阶段下拉依次完成余下流程。

### 3 · 动作清理与人工修正

AI 动作通常先直接建立人工修正层；视频动捕噪声较明显时，再使用“复制并清理动捕”。清理会复制 Action，不修改 RAW：

- `轻度`：尽量保留快速细节；
- `标准`：一般全身动捕的起点；
- `强力`：抖动明显时使用，但可能削弱击打和急停。

四元数和轴角旋转不会被错误地按欧拉曲线平滑。人工修正层用于脚底接触、骨盆高度、膝肘方向、穿模、手持武器和角色表演节奏；手指、表情、裙摆、头发与武器约束不属于自动主链映射。

### 4 · 镜头与灯光

先选择景别，再创建快速目标相机或 Add Camera Rigs 专业 Rig。用时间线切镜标记组织镜头，最后创建 Key/Fill/Rim 三点光。自动灯光提供可用起点，不替代针对皮肤、头发高光、光环和场景氛围的艺术调整。

### 5 · 预览、检查与安全清理

1. “准备预览输出”设置适合快速检查的输出参数。
2. “交付检查”确认相机、角色动作、帧范围和输出路径等必要状态。
3. “清理 Bridge 临时资源”只处理带 `bam_owner=ba_motion_bridge` 与 temporary 标记的未使用数据。
4. “清理工程缓存”只处理项目 UUID 与 sentinel 同时匹配的 `50_cache/baw_generated`。

工具不会执行全局 Orphan Purge，也不会删除 RETARGET_OUTPUT、MMD preset、模型、贴图、音频、渲染、工程文件或备份。最终交付前仍应手动保存新版本并确认输出目录。

## 传统视频动捕路径

BlendCap 视频动捕不经过 Proscenium。打开 `BA 动画 → 分步制作 → 传统 BVH`：

1. 在 BlendCap 完成视频推理并得到 BVH/源骨架。
2. 选择 BVH 来源与 MMD 目标。
3. 需要裙发缓冲时，在同一面板启用“起始缓冲”，选择当前姿态、Rest Pose 或指定 Action 帧，并填写静置帧和过渡帧数。
4. 点击“自动准备并安全重定向”。BlendCap Motion Bridge 0.4.0 会保持正式动作原首帧不动，仅在它之前写入负帧预滚动键并顺序求值物理。
5. 完成裙发物理烘焙后勾选确认项，再清理预滚动；清理只删除正式首帧之前的缓冲键，不平移正式动作。
6. 回到“3 · 动作修正”处理噪声、脚滑与接触。

这个折叠区保留传统兼容路径，但它与官方 SOMA → 角色的 Proscenium Motion Bridge 是两条独立管线，不应混用映射表。

## 恢复与排错

### 输出后想切回旧动作

在 `Proscenium` 的 Bridge 输出区或 `BA 动画` 的 AI 动作区点击“恢复角色原状态”。它会按可用快照恢复目标动画状态、IK/FK 和腿链约束。新输出 Action 仍保留，可稍后再次激活；本插件没有 BlendCap 映射需要恢复。

### 找不到官方骨架

重新导入 Canonical Skeleton，并确认它保留 `proscenium_canonical_model=kimodo-soma-rp` 标记和官方 30 骨签名。Bridge 会拒绝仅靠改名或伪造单个标记的骨架。

### MMD 目标检查失败

- 确认选择人体主 Armature；
- 应用非等比对象缩放后重新检查；
- 不要用 IK、捩、影骨代替主 FK 骨；
- 确认大腿、小腿、脚、上臂、前臂、手、颈、头和骨盆主链存在。

### 已 Accept 但提示没有动画

确认 `Proscenium: Motion` NLA Track/Strip 没有 mute、Strip influence 大于 0，并检查官方骨架是否仍是 Bridge 源。Bridge 支持 Accept 后只有 NLA、没有活动 Action 的状态。

### 脚滑、穿地或武器接触不准

重定向解决的是骨架语义、Rest Pose 和数据安全，不是自动脚锁或道具约束。先回到提示词、Root Path 和 Foot Pins 减少源动作问题，再用 CORR 层做角色特定修正。

### 组件显示“已启用但未就绪”

展开单一主面板底部的“组件诊断”。这通常表示模块存在但必要操作符没有完整注册；不要继续输出，先重启 Blender，并核对版本是否为本指南顶部的组合。

## 当前验证边界

确定性测试已覆盖官方骨架到真实星野 MMD 主链 `24/24`、Accepted NLA 输入、独立输出 Action、世界空间 Rest Pose 适配、约束与映射恢复、故障回滚和临时数据清理。

这些结果证明重定向管线和数据安全，不代表每条自然语言提示都能生成理想表演。当前没有登录 Animatica 执行付费 Hosted Generate；脚滑、穿模、武器接触和人工修复时间仍应使用你的固定 10–15 秒黄金镜头持续记录。
