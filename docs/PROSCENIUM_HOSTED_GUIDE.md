# Animatica Proscenium Hosted 使用指导

历史文档说明（2026-09-07）：此文记录旧环境，不代表当前安装状态。文中旧配置备份和 smoke 工程目前未在本任务目录找到，不能直接用于恢复。仍保留的第三方安装包位于下方更新路径；上游维护归属 Motion_Bridge。

适用环境：Blender 5.1.2 / Proscenium 0.4.0  
安装日期：2026-08-29  
运行模式：Animatica Cloud（Hosted）

## 当前状态

已经完成：

- 从 [Animatica 官方 v0.4.0 Release](https://github.com/animatica-ai/animatica-blender-plugin/releases/tag/v0.4.0)下载唯一安装资产 `proscenium-blender-0.4.0.zip`；
- 安装包大小 650,630 字节，SHA-256 与 GitHub 发布元数据一致：

  ```text
  64a9d76c001be20e132ee236313ae244e98c38d2ef3b196c96d979ba4faf21b1
  ```

- 在隔离配置中完成安装、启用、注销/重新注册、保存和重开测试；
- 安装到 Blender 5.1 正式配置并启用；
- 当前配套版本锁定为 MMD Tools 4.5.13、BA Animation Workflow 0.7.0、Proscenium Motion Bridge 0.9.1 与 Add Camera Rigs 1.8.2；传统 BVH 路线另配 BlendCap 1.0.5 和 BlendCap Motion Bridge 0.4.0；
- Hosted 模式开启，Self-hosted 关闭；
- `https://api.animatica.ai/mmcp` 连通，公开模型列表包含 `kimodo-soma-rp`；
- 成功导入 30 骨官方 Canonical Skeleton，按 30fps 保存并重开测试文件；
- 未下载 Kimodo、PyTorch、CUDA、venv 或模型权重；
- 尚未登录 Animatica，因此未消耗任何生成额度。

安装位置：

```text
C:\Users\Administrator\AppData\Roaming\Blender Foundation\Blender\5.1\scripts\addons\proscenium_blender
```

官方安装包归档：

```text
D:\Agent Workspaces\Agent Tools\BA_Animation_Workflow\dependencies\third_party\animatica\proscenium-blender-0.4.0.zip
```

安装前配置备份：

```text
D:\Agent Workspaces\BA_Animation_Workflow\backups\profile-pre-proscenium-20260829-201436
```

参考骨架测试工程：

```text
D:\Agent Workspaces\BA_Animation_Workflow\smoke_runs\proscenium-hosted-0.4.0\canonical_skeleton_smoke.blend
```

## 第一次登录

v0.4.0 没有浏览器 OAuth。为了不把密码写进命令或日志，登录必须由你在 Blender 内完成一次：

1. 如果还没有账号，先在 [Animatica 注册页](https://app.animatica.ai/signup?from=blender)创建免费账号。
2. 打开：`编辑 → 偏好设置 → 插件`。
3. 搜索 `Proscenium`，展开 `Proscenium — AI Motion Generation`。
4. 确认 **Self-hosted 没有勾选**。
5. 点击 **Sign in**，输入 Animatica 邮箱和密码。
6. 关闭偏好设置；Blender 会保存登录 token，之后通常不必重复输入密码。

密码只在登录请求期间使用，不会保存；但 access token、refresh token、邮箱和套餐会写进 Blender 的 `userpref.blend`。界面的密码遮罩不等于 Windows 加密保险库，因此登录后的这个文件应按敏感配置对待：

```text
C:\Users\Administrator\AppData\Roaming\Blender Foundation\Blender\5.1\config\userpref.blend
```

不要把登录后的 `userpref.blend` 发给别人，也不要把它上传到版本库或公共网盘。

## 第一次生成：只用官方参考骨架

不要直接拿正式《蔚蓝档案》工程做第一次试验。

1. 新建一个空白 `.blend`。
2. 将场景设为 **30fps**，帧范围设为 `1–60`。
3. 在 3D 视图按 `N`，选择右侧 **Proscenium** 标签。Connect、导入、Generate、Preview、Accept/Reject 与 Proscenium Motion Bridge 的角色输出都在这个动作阶段标签内。
4. 点击 **连接/刷新模型**。
5. 模型选择 `kimodo-soma-rp`。
6. 点击 **Import kimodo-soma-rp skeleton**，先使用官方参考骨架。
7. 在 Timeline 的 `Proscenium` 轨道空白处双击，创建 Prompt Block。
8. 再双击色块输入提示词；输入中文时应右键色块选择 **Edit Prompt**，但 Kimodo 仍建议使用具体英文。
9. 保持 Settings 中：

   - Quality：`Standard`
   - Text Weight：`2.0`
   - Constraint Weight：`2.0`
   - Motion Cleanup：开启
   - Transition Frames：`5`
   - In Place：走路测试时关闭

10. 点击 **Generate Motion**。
11. 播放预览：

    - 不满意：点击 **Reject**，原动作会恢复；
    - 只测试官方骨架：点击 Proscenium 原生 **Accept**。v0.4.0 的按钮文字有时显示为 **Push to NLA**，会把结果保留为普通 Action/NLA 动作；
    - 已导入角色：在同一标签的 `Proscenium Motion Bridge` 选择源/目标并点击“接受并输出到角色”，一次完成 Accept、检查和独立 Action 输出。

第一条提示词：

```text
A person walks forward slowly for two steps, stops, and stands balanced.
```

第二条完整测试：

```text
A person stands relaxed, takes two light steps forward, stops,
raises the right hand, waves twice, and returns to a relaxed standing pose.
```

云端长时间闲置后的第一次生成可能超过一分钟。不要中途强制关闭 Blender。`Cancel` 只停止 Blender 等待，服务器请求可能仍在继续并消耗额度；确实不想要结果时，生成完成后用 Reject 更稳妥。

## 怎样提高精度

只写“可爱地战斗”之类风格词，结果会很随机。精度主要来自四层约束：

### 1. Prompt Block

写出起始姿势、动作顺序、左右、方向、速度、停顿和结束姿势：

```text
A young woman starts in a low ready stance, takes two quick steps forward,
raises both hands to aim a rifle to the front-left, holds for one second,
then returns to a balanced standing pose.
```

模型不会知道枪械的真实几何尺寸，因此这只生成身体底稿，握把和枪托接触仍需后续修复。

### 2. 关键姿势

在最重要的帧给目标骨架摆姿势并打少量关键帧，例如：

- 第 1 帧：起始警戒姿势；
- 第 30 帧：举枪瞄准剪影；
- 第 60 帧：结束站姿。

Kimodo 会把这些关键帧视为硬约束，再补完中间运动。这比仅靠文字稳定得多。

### 3. Root Path

在 `Constraints` 面板创建地面路径，控制角色整体移动方向。需要原地待机时才启用 `In Place`。

### 4. Hand/Foot Pins

手扶桌、脚踩台阶或固定握枪接触时，在相应帧创建手脚目标。不要同时固定过多关节，否则动作会僵硬或约束冲突。

## 接入 MMD /《蔚蓝档案》角色

按以下顺序逐步晋级：

### 路线 A：Hosted 直接生成到角色副本

1. 复制角色 `.blend`，绝不使用唯一正式文件。
2. 只选择主要人体 Armature 作为 Target Armature。
3. 先生成待机、走两步、挥手三种简单动作。
4. 检查骨盆 Root、左右侧、肩肘扭曲、膝盖、脚滑和辅助骨。
5. 只在副本中 Accept；通过后再把 Action 迁移进正式镜头。

Hosted 支持自定义 Armature，但 MMD 有 IK、捩骨、辅助骨、裙骨和日文骨名，直接结果不一定稳定。

### 路线 B：Canonical Skeleton → Proscenium Motion Bridge（推荐）

这是当前默认且最稳健的路线：

```text
Proscenium 官方 kimodo-soma-rp
  → Preview
  → 接受并输出到角色（Proscenium Motion Bridge 0.9.1）
  → 独立 MMD RETARGET Action
  → BA Animation Workflow 0.7.0 CLEAN / CORR
```

保持在 `N → Proscenium`，在唯一的 `Proscenium Motion Bridge` 面板选择官方源骨架与角色目标，选择 `完整位移`（24 对）或 `原地动作`（22 对），再点“自动识别并检查”。Preview 满意后直接点“接受并输出到角色”；若动作已经 Accept，按钮显示“一键输出到角色”。Bridge 能读取活动 Action 或 Accept 后的 NLA，使用自身的世界空间重定向器与静置方向补偿，并支持 MMD FK 与 Auto-Rig Pro FK 控制链。

完成后可点“恢复角色原状态”一次恢复目标动画、IK/FK 与腿链约束。Bridge 使用自己的映射表和 bake，不读写 BlendCap；BlendCap Motion Bridge 0.4.0 仍只用于 BlendCap BVH，其 `LeftLeg=小腿` 假设不适用于 SOMA 的 `LeftLeg=大腿`。

统一动作入口不等于合并插件。BA Animation Workflow、Proscenium Motion Bridge 与 BlendCap Motion Bridge 仍是三个独立技术包，Proscenium 也保持第三方插件边界；各包拥有独立 manifest、版本和注册生命周期。

详细步骤、映射表和排错见 `docs/BA_MOTION_BRIDGE_GUIDE.md`。

无论使用哪条路线，都要保留：

```text
ACT_<角色>_<动作>_AI_RAW
ACT_<角色>_<动作>_RETARGET
ACT_<角色>_<动作>_CLEAN
ACT_<角色>_<动作>_CORR
```

RAW 永不覆盖。手指、表情、头发、裙摆、武器接触和二次元节奏集中放在 CORR/NLA 修正层。

## 数据与隐私边界

一次 Hosted 生成会发送：

- 提示词和持续帧数；
- 骨骼名称、父子层级和静止位置；
- 关键姿势的关节旋转；
- Root 路径、手脚目标和生成设置。

插件源码没有上传角色网格、贴图或整个 `.blend`。不过 Prompt Block 会作为骨架自定义属性保存在 `.blend` 中，分享工程前应检查提示词是否适合一并公开。

云端首轮只用官方参考骨架或无版权代理角色；确认流程后再决定是否让服务处理正式角色的骨架结构。

## 一个必须遵守的安全规则

Proscenium 0.4.0 在 Hosted 登录状态下切换到 Self-hosted，可能把缓存的 Bearer token 发给自定义服务器；自托管端返回 401 时，甚至可能把 refresh token 发往其 `/auth/refresh`。

因此：

> 将来若要改用本地 Kimodo，必须先在 Proscenium 中点击 Sign out，保存偏好并重启 Blender，确认已经退出后，才能勾选 Self-hosted。

本次安装已保持 Self-hosted 关闭，也没有配置任何本地服务器。

## 常见问题

### 看不到 BA 动画或 Proscenium 标签

- 确认使用的是 `D:\softwares\Blender Foundation\Blender 5.1\blender.exe`，不是 Steam Blender 5.2；
- 在 3D View 内按 `N`；
- 在偏好设置中确认 `BA Animation Workflow` 与 `Proscenium Motion Bridge` 已勾选；
- 在偏好设置中确认 `Proscenium — AI Motion Generation` 已勾选。

### Connect 失败

- 确认 Self-hosted 关闭；
- 确认已经 Sign in；
- 检查是否能访问 `https://api.animatica.ai`；
- 不要把 Server URL 改成 localhost。

### 动作左右反了或脚滑

- 提示词明确写 `left/right`；
- 用关键姿势固定起始和结束方向；
- 使用 Root Path；
- 保持 Motion Cleanup 开启；
- 到 BA Workflow 的 CLEAN/CORR 层做最后脚锁和接触修复。

### 生成后想回到原动作

在预览阶段点击 Reject。Accept 后也不要编辑 RAW，先复制 Action 再清理。禁用或卸载插件不会删除已经 Bake/Accept 的普通 Blender Action。

## 卸载和回滚

普通卸载：

1. 等待当前生成完成；
2. 在插件中 Sign out，并保存偏好；
3. 禁用 Proscenium，保存偏好并退出 Blender；
4. 只移除 `scripts\addons\proscenium_blender`；
5. 重启 Blender，确认没有注册报错。

需要完全恢复安装前状态时，退出全部 Blender 进程，再用以下备份恢复 `userpref.blend`：

```text
D:\Agent Workspaces\BA_Animation_Workflow\backups\profile-pre-proscenium-20260829-201436\userpref.blend
```

不要在 Blender 运行时覆盖偏好文件。

## 官方资料

- [插件 Release](https://github.com/animatica-ai/animatica-blender-plugin/releases/tag/v0.4.0)
- [官方使用说明](https://github.com/animatica-ai/animatica-blender-plugin/blob/v0.4.0/docs/usage.md)
- [登录与配置](https://github.com/animatica-ai/animatica-blender-plugin/blob/v0.4.0/docs/configuration.md)
- [限制说明](https://github.com/animatica-ai/animatica-blender-plugin/blob/v0.4.0/docs/limitations.md)
- [Animatica 服务介绍](https://animatica.ai/kimodo)
