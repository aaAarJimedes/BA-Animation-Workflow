# BA Animation Workflow

面向 Blender 5.1.2 与 MMD/《蔚蓝档案》角色的一站式动画工作流。当前版本组合：

- BA Animation Workflow 0.9.0：实验防突变支持「仅当前段 / 前后均分」，默认保持单侧；均分使用总窗口、成对备份，重复映射先撤回旧修正，保护人工编辑与窗口外动作；
- Proscenium Motion Bridge 0.9.1：把 Proscenium 官方 `kimodo-soma-rp` 动画稳健输出到 MMD 或 Auto-Rig Pro 控制器骨架，并支持跟随目标初始布置的动作空间、可调肢端防穿模、起始缓冲、负帧物理预滚动与多角色恢复；
- BlendCap Motion Bridge 0.4.0：把传统 BlendCap/BVH 动捕自动准备并安全重定向到 MMD，并用负帧预滚动缓解正式首帧的裙发穿模；
- Proscenium Hosted 0.4.0、BlendCap 1.0.5、MMD Tools 4.5.13、Add Camera Rigs 1.8.2。

## 统一 UX，不合并技术包

动作阶段集中在 `N → Proscenium`。Proscenium Motion Bridge 0.9.1 只注册一个整洁面板，并按“选择骨架 → 输出设置 → 识别与检查 → 输出动作 → 输出结果”的工作流顺序排列。“输出设置”可决定动作是否跟随角色的当前位置与水平朝向，并可开启或调整肢端防穿模；起始缓冲仍支持当前姿态、Rest Pose 或指定 Action 帧。

制作阶段集中在 `N → BA 动画` 的唯一主面板。BA Animation Workflow 0.9.0 顶部只有“全自动 / 分步制作”模式切换：全自动模式显示角色、当前 Clip 多行文本、总帧数、状态和一个主运行键。点击“新建并打开多行提示词”会拆分出 Blender 文本编辑器；文本整体作为一个动作段，帧率沿用当前场景，生成范围从当前帧开始。切换角色后，工作流会在请求生成前保留上一角色的桥接输出并释放其一键恢复点，再安全绑定新角色。负滚动预热只需设置过渡边距；连续 Clip 会读取当前最终可见姿态，根运动链只在最高层恢复可见位置/朝向，`センター → グルーブ` 等子链直接沿用上一段局部位移；身体骨骼约用四分之一秒从上一姿态平滑过渡回 Proscenium 原始动作。“动作复用”区先选择动作文本块，再自动显示其当前关联 Action；打开旧工程以及真正点击操作时都会根据实际源动作提示词重新解析，真实源提示词优先于旧 Clip ID。覆盖前还会验证旧 Action 确实属于同一文本块，并自动修复旧版误替换的 BA 自有 NLA 条带。所有复用操作都不调用动作生成服务。场景、灯光、构图默认全部关闭。

统一入口不等于代码耦合。BA Animation Workflow、Proscenium Motion Bridge 与 BlendCap Motion Bridge 仍是三个独立技术包，可以分别安装、启用、升级和排错；第三方 Proscenium 也保持独立。Proscenium Motion Bridge 只调用 Proscenium 的公开 Accept 操作符，映射表与烘焙求解全部自有，不导入、调用或改写 BlendCap。

## 最短 AI 动作路径

### 实验性全自动路径

1. 导入用户模型并选择角色 Armature，保存工程副本。
2. 打开 `N → BA 动画 → 实验性 · AI 自动导演`，指定“角色骨架”。
3. 把时间轴移到新动作的正式起点，点击“新建并打开多行提示词”，输入一个动作段，并在“当前 Clip 总帧数”填写长度。提示词中的 FPS、帧范围、Timeline 或 Pose Anchors 不会被解析为调度指令。
4. 可先点“生成导演方案”或“仅搭建场景”检查结果；方案会写入只属于当前场景的 `BAW_自动导演方案` 文本块。
5. 检查“生成后自动接受并输出”开关。开启时，点击“生成当前 Clip 动作”会在成功后自动 Accept 并重定向；关闭时，流程停在 Proscenium Preview 等待手动验收。当前角色没有动作或当前帧位于时间轴起点时，会从“负滚动过渡边距”指定的位置开始，逐帧平滑进入正式首姿；否则把上一段活动 Action 保留到 NLA，并把当前角色姿态写入新 Action 的首帧。
6. 首次使用 Animatica Cloud 仍需用户事先完成登录；冷启动可能超过 60 秒。面板会异步轮询，不会用阻塞等待卡住 Blender。

当前“AI 动作”由 Proscenium 提供；场景、灯光和镜头是可审计的本地提示词方案编译器与程序化模板，不会把模型或创作描述额外发送给其他场景生成服务。它不会自动生成任意精细资产、表情、手指、武器接触或裙发物理。完整边界、状态机与故障恢复见[实验性自动导演说明](docs/EXPERIMENTAL_AUTO_DIRECTOR.md)。

### 分阶段可控路径

1. 启动 `D:\softwares\Blender Foundation\Blender 5.1\blender.exe`，不要误用 Steam Blender 5.2。
2. 打开角色工程副本，用 MMD Tools 导入角色；在 `BA 动画` 选择项目目录并“一键初始化动画工程”。
3. 切到 `Proscenium`，连接服务、选择 `kimodo-soma-rp` 并导入官方 Canonical Skeleton。
4. 在 Timeline 创建 Prompt Block，写清动作顺序、左右、方向、速度、停顿和结束姿势，然后 Generate。
5. 预览满意后，在同一 `Proscenium` 标签的 `Proscenium Motion Bridge` 选择官方源骨架和角色 Armature。
6. 选择“完整位移”或“原地动作”，点“自动识别并检查”；确认主链为 `24/24` 或 `22/22` 且没有关键缺失。
7. 仍在预览时点击“接受并输出到 MMD”。Bridge 会 Accept、复查并输出独立 `ACT_<角色>_<动作>_MMD` Action；若已经 Accept，则点“一键输出到 MMD”。
8. 回到 `BA 动画` 建立 CORR 人工修正层，处理脚滑、穿模、手部/武器接触和表演节奏。
9. 创建镜头、切镜标记和三点光，再准备预览并运行交付检查。
10. 需要清理时只用工作台的安全清理按钮；它们只处理带本工具所有权标记的缓存或临时数据。

传统视频动捕走 `BA 动画 → 传统视频动捕 · BlendCap → MMD`，使用 BlendCap Motion Bridge 0.4.0 的“自动准备并安全重定向”。需要裙发物理缓冲时，可在重定向前选择当前姿态、Rest Pose 或指定 Action 帧作为起点；缓冲键只写到正式首帧之前的负帧预滚动区，正式动作首帧保持不变。不要把官方 SOMA 骨架交给传统 Detect：SOMA 的 `LeftLeg` 是大腿，而常见 BVH 语义不同。

完整的新手步骤、状态说明与排错见 [BA Animation Workflow 一站式使用指南](docs/BA_ANIMATION_WORKFLOW_GUIDE.md)。

## 三个技术包的边界

| 包 | 自动处理 | 不负责 |
|---|---|---|
| BA Animation Workflow 0.9.0 | 文本块主索引、真实源提示词优先的双重关联校验、覆盖前同源验证、误替换 NLA 自动恢复、稳定 Clip ID、同文本同模型动作接管、孤立 Proscenium 源动作恢复、自动处理跨角色恢复点、上下文单主键动作复用、原生多行提示词、锁定所选文本的逐段/批量导入、已有动作无生成原位替换、单段总帧数、当前帧放置、上一段 Action 与负滚动区完整保留、无重复父级位移的根运动继承、身体首帧短过渡、辅助骨状态保护、PMB 0.9.1 输出策略、可选场景/灯光/镜头、工程初始化、CORR 层、预览、审计和所有权安全清理 | 提示词内分段调度、Pose Anchor 自动生成、Proscenium 模型推理、骨架求解器、MMD 导入、精细资产生成 |
| Proscenium Motion Bridge 0.9.1 | 自有 SOMA → MMD/Auto-Rig Pro 映射与 bake、目标初始布置动作空间、可调肢端防穿模、起始缓冲、负帧物理预滚动、多角色恢复点、独立 Action 与事务回滚 | 手指、表情、裙发、武器接触和艺术修正 |
| BlendCap Motion Bridge 0.4.0 | BlendCap/BVH → MMD 映射准备、preset、安全重定向、负帧预滚动、表情与 VMD 后处理 | Proscenium SOMA 语义和 AI 动作生成 |

Bridge 的默认安全边界：

- 只接受带官方模型标记且满足 30 骨签名的 `kimodo-soma-rp` 源；
- 完整位移映射 24 对，原地映射 22 对；关键主链不完整时拒绝执行；
- 使用插件自有的世界空间、rest-aware bake，检测到非等比对象缩放时停止；
- Root 比例只使用髋、头、脚、肩和手等身体 landmark，避免光环、头发和武器污染；
- 只临时处理已映射腿链 IK 与明确的腰取消约束，不批量关闭手臂、裙发、附件和物理约束；
- 新建独立输出 Action，不覆写原 Action/NLA；失败自动恢复 Bridge 已修改的状态；
- Proscenium Accept 已成功而后续重定向失败时，已接受动作仍保留，可修正目标后重试；
- SOMA 映射保存在插件自身状态中，不读取或改写 BlendCap 的映射表与 preset。

## 已验证边界

确定性官方骨架 → 真实星野 MMD 测试覆盖：

- 主链 `24/24`，关键缺失 0；
- 20 帧 Accepted NLA 输入输出 1,880 个关键帧点；
- `Chest → 上半身2` 世界旋转增量误差 `0.0°`；
- 体型位移比例 `0.6829482317`；
- 只记录 6 个腿链/腰取消约束快照，未相关约束不变；
- 原 Action、Action Slot、NLA 与约束状态均可恢复；
- 故障注入后 Bridge 修改的动画、约束和时间轴状态全部回滚；
- 临时 Action 残留 0。

真实角色测试使用隔离副本且从未保存。当前没有登录 Animatica 执行会消耗额度的 Hosted Generate；上述结果证明重定向管线与数据安全，不等于自然语言生成质量。脚滑、穿模、武器接触和人工修复时间仍需用固定 10–15 秒黄金动作持续评估。

## 清理策略

- BA Workflow 只清理项目 UUID 与 sentinel 同时匹配的 `50_cache/baw_generated`；
- Motion Bridge 只清理带自身 owner + temporary 标记的未使用临时数据；
- RAW、RETARGET_OUTPUT、MMD preset、模型、贴图、音频、渲染、`.blend` 和备份不会被自动删除；
- 不执行全局 Orphan Purge。

## 安装与回滚

三个自研包保持独立发布。目标包名为：

- `ba_animation_workflow-0.9.0.zip`
- `proscenium_motion_bridge-0.9.1.zip`
- `blendcap_motion_bridge-0.4.0.zip`

退出所有 Blender 后，使用 `tools/install_real_profile.ps1` 升级正式 Blender 5.1 profile。脚本会先备份偏好和被替换的扩展，安装后运行正式 profile smoke；任一步失败都会恢复旧版。不要在 Blender 运行时覆盖 `userpref.blend` 或扩展目录。

最终 ZIP 的大小、SHA-256、正式安装版本、smoke 结果与具体回滚目录记录在 [验证记录](docs/VALIDATION.md)，不要使用目录中仍可能保留的旧版本 ZIP。

## 文档

- [一站式使用指南](docs/BA_ANIMATION_WORKFLOW_GUIDE.md)：两个标签、AI/传统动捕主线、分阶段制作与排错；
- [实验性自动导演](docs/EXPERIMENTAL_AUTO_DIRECTOR.md)：全自动状态机、方案编译、所有权边界与限制；
- [Proscenium Motion Bridge 指南](docs/BA_MOTION_BRIDGE_GUIDE.md)：MMD/Auto-Rig Pro 映射、静置姿态补偿、约束与恢复细节；
- [Proscenium Hosted 指南](docs/PROSCENIUM_HOSTED_GUIDE.md)：登录、Prompt、约束和隐私边界；
- [验证记录](docs/VALIDATION.md)：构建、安装和真实骨架测试证据；
- [自然语言动作调研](docs/AI_TEXT_TO_MOTION_RESEARCH.md)：方案比较与选型依据；
- `config/addons.lock.json`、`config/cleanup-policy.json`：正式版本锁与清理边界。

插件许可证不等于模型、动作、音乐或《蔚蓝档案》角色资产的授权。公开或商业发布前仍需核对每项素材的作者说明与许可范围。
