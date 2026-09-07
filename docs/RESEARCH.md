# 工具调研与取舍

调研日期：2026-08-29；SOMA/MMD 桥接更新：2026-08-30

> 历史快照：本文保留选型当时的版本、面板设计和安装状态，不代表当前正式配置。当前发布组合与使用路径以 `README.md`、`docs/BA_ANIMATION_WORKFLOW_GUIDE.md` 和 `docs/VALIDATION.md` 为准。

## 结论

调研时机器已经具备最难替代的两段：BlendCap 1.0.5 和自制 BlendCap Motion Bridge 0.1.12。最优方案不是继续堆动捕/重定向插件，而是围绕现有链补齐非破坏动作修正、镜头控制、灯光起点、项目治理和交付检查。

## 保留与新增

### 保留：BlendCap 1.0.5

本机已有两份捕获日志完成到 100%，证明链路实际可用。其单视频身体、手、脸捕捉覆盖了最耗时的“古法 K 帧”底稿。公开源码和说明见 [BlendCap](https://github.com/Arcomade/BlendCap)。

### 保留：MMD Tools 4.5.13

本机已安装官方扩展且能加载，负责 PMX/PMD、VMD/VPD、材质、刚体和 MMD 编辑。4.5.13 声明兼容 Blender 4.2+，来源为 [Blender Extensions](https://extensions.blender.org/add-ons/mmd-tools/)。

### 保留：BlendCap Motion Bridge 0.1.12

已有 12 份角色映射，直接解决 BlendCap 到 MMD 骨架的适配。该插件依赖 BlendCap 的属性和操作符但未锁版本，因此 BlendCap 升级前必须跑黄金角色回归。

### 新增：Add Camera Rigs 1.8.2

官方扩展，兼容 Blender 4.2+；提供 Dolly、Crane、2D Rig、Aim、DOF、Dolly Zoom 与时间线相机绑定，权限为空。它减少镜头约束搭建，但不会替用户决定构图。[Add Camera Rigs](https://extensions.blender.org/add-ons/add-camera-rigs/)

### 新增：BA Animation Workflow 0.2.0 + BA Motion Bridge 0.1.0

BA Workflow 继续负责编排和安全默认值：项目结构、Action 副本清理、NLA 修正层、快速镜头、三点光、预览和检查。0.2.0 把 Proscenium、Motion Bridge 和传统 BlendCap Motion Bridge 常用入口集中到同一 `BA 动画` 面板。

Motion Bridge 解决此前缺失的稳定边界：自然语言只生成到官方 `kimodo-soma-rp`，再用独立的 SOMA 语义 profile、MMD 日/英 metadata 与层级解析、BlendCap Classic 世界空间 rest-aware bake 转到 MMD。它拒绝部分关键主链、重复旋转目标、位移轴冲突和非等比对象缩放；Root 比例只使用身体 landmark，不受头发、武器、光环影响。

旧 BlendCap Motion Bridge 的 BVH 假设是 `LeftUpLeg=大腿 / LeftLeg=小腿`，而 SOMA 是 `LeftLeg=大腿 / LeftShin=小腿`。因此传统 Detect 不能用于官方骨架。Bridge 不写 preset，只用内存表，并提供旧表、约束和目标 Action/NLA 的精确恢复。

两个本地扩展都不联网，不覆盖原始 Action，不执行全局 Orphan Purge。项目与缓存采用 UUID 双标记；盘符根、Blender 配置/安装目录、符号链接、junction 与 dangling reparse point 都会被拒绝。灯光不会覆盖用户 World，同名用户数据也不会被接管。

## 明确未安装

- Retarget：Blender 5+ 版本可用，并含 MMD preset 和曲线工具，但与现有 BlendCap Motion Bridge 的核心作用重复，故只在面板显示状态，不安装。[Retarget](https://extensions.blender.org/add-ons/retarget/)
- AutoCam：适合驾驶式录制相机，但当前已有 CurveMotion、快速相机构图和 Add Camera Rigs；先不引入第四套镜头逻辑。
- 额外面捕/口型插件：BlendCap 已覆盖脸部。只有对白项目暴露明确缺口时，再用固定音频做单独评估。
- 旧 AnimAide：磁盘已无文件、偏好仍残留并导致每次启动报错，已只清除失效启用项。
- Rigify/Auto-Rig Pro/Rokoko：会增加一层骨架与映射，和当前 BlendCap Motion Bridge 目标冲突。

## Blender 版本选择

本机 5.1.2 是实际生产配置，BlendCap、MMD Tools、BlendCap Motion Bridge、CurveMotion 均已在此加载。虽然机器上另有 Steam Blender 5.2.1 LTS，但其用户配置为空。当前阶段固定 5.1.2；迁移 5.2 时应复制配置而不是覆盖，并完成插件加载、同角色重定向、动作清理、保存重开和三帧渲染测试。

Blender 5.1 的 Action 已采用分层/分槽 API；旧代码直接访问 `Action.fcurves` 会失败。本工具已经按 `layers → strips → channelbags → fcurves` 结构实现。官方 API 见 [Blender 5.1 Python API](https://docs.blender.org/api/5.1/)。

动作清理的首版边界是：欧拉角先解除 ±π 跳变再清理；四元数和轴角旋转为避免逐分量处理造成翻转，暂时原样保留。多 slot Action 会明确拒绝自动处理，需先拆分为单目标 Action。

## 输出策略

面板的 H.264 只用于快速预览。最终动画使用 PNG 或 OpenEXR 图像序列，便于崩溃后续渲和后期调整，再用 Blender VSE、Adobe Media Encoder 或 Premiere 编码。Blender 5.1 的媒体类型和视频输出界面已变化，测试已覆盖 `media_type=VIDEO`。

## 后续最有价值的单项实验

选择一名映射成熟的常用角色和一段 10–15 秒素材，包含走路、转身、挥手、抬脚和对白：

1. 记录 BlendCap 和 BlendCap Motion Bridge 用时。
2. 记录 RAW、CLEAN、CORR 关键帧数。
3. 测量脚接触段滑移、穿地、手部接触和肩肘错误。
4. 建三个镜头，统计首次预览总用时。
5. 关闭本地编排扩展，确认已烘焙动作、相机和灯光仍可工作。

只有这个固定测试通过，才应继续评估口型、次级运动或灯光管理插件。
