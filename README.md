# BA Animation Workflow

Blender 5.1 的单段动作制作、复用和收尾工具。当前版本 **0.14.0**。

## 使用

安装 `ba_animation_workflow-0.14.0.zip`，在 `N → BA 动画` 中展开所需功能。动作制作与镜头、部件分离、道具、物理、交付可独立展开。生成依赖独立安装的 Proscenium 与 Proscenium Motion Bridge；两者不包含在本包内。

0.14 优化部件识别和校验速度，防止换目标后沿用旧分组；快速预览保留 FPS 和时间范围。物理高级参数默认收起。详细实测见 [优化记录](docs/VALIDATION_0.14.0.md)。

- 一个 Clip 对应一个动作提示。编辑器只粘贴英文动作内容，帧数在面板设置。YAML、Markdown 包装和关键帧说明会明确报错，避免把整份制作方案当成动作提交。
- 面板显示 `N/1000` 字符及按场景真实 FPS 计算的时长。插件不会为匹配示例擅自更改场景帧率。
- 动作复用保留文本和源 Action 的可靠关联、防脚滑、单侧/前后均分接缝，以及重复操作和失败恢复保护。修改较早的均分接缝前，需从后向前撤回相连修正，避免破坏后段或人工修改。

## 人物部件识别与分离

新增本地候选识别：综合材质、静置位置、骨骼权重和几何连接，区分服装、左右鞋袜、下装及饰品。先彩色预览，可人工补选、替换分组，再生成分离副本并保留原模型。逐部件检查顶点、形态键、UV、权重、材质、法线和骨架绑定；同一部件跨多个网格时归入同一子集合，不强制合并不同形态键系统。可切回原模型。

这是可纠正的规则识别，尚未接入图像 AI；不自动补身体或为服饰另建物理骨架。用法与支持范围见 [部件分离说明](docs/PARTS_GUIDE.md)。

## MMD 物理与安全烘焙

新增独立的物理面板：检查绑定与完整预热范围，在后台副本中连续模拟，再逐帧验证并应用为可恢复的骨骼 Action。保留 FPS、负帧和原动作，规避 Blender 5.1 缓存第 0 帧跳变；刚体布局只有在多个关节提供一致证据时才在副本中校正。支持 Esc 取消和恢复烘焙前状态。

需要独立启用 MMD Tools。当前支持单角色动态系统、单层 Action 和内存缓存；完整使用方法及限制见 [物理说明](docs/PHYSICS_GUIDE.md)，实际验证见 [0.11.0 验证记录](docs/VALIDATION_0.11.0.md)。

## 道具接触与动作检查

在子面板选择角色、道具、持握骨骼和帧范围。先在开始帧将道具摆进手中，再烘焙持握。工具按照已有手部动作生成独立的道具 Action，在放下帧以后保持释放位置；原角色动作不会被改动。恢复按钮撤回本工具的道具 Action。

道具应是本场景中可编辑、无父级、无约束、无动画的独立对象。工具不会自动修改手的接触位置；应先修好手的抓取/放下动作。双手道具需要人工保证第二只手的握点。

“检查停顿与速度”只采样手和头部，输出低速区间及峰值帧的文本报告。它不自动删帧，低速候选也不等同于错误；有意停留和接触姿态应保留。

## 渲染规划与资源交付

新增资源检查与安全打包：区分真实依赖、已内嵌素材和追加来源记录。可导出绑定已保存源版本的分段计划，保留 FPS 与预热，拒绝混用变更后的工程。计划仅用于规划，不会自动渲染或拼接。见 [交付说明](docs/DELIVERY_GUIDE.md)。

可复用的 Codex 工作流随源码维护于 [skills/blender-animation-polish](skills/blender-animation-polish/SKILL.md)，不打入 Blender 扩展 ZIP。

## 开发结构

`extension/ba_animation_workflow/clip_plan.py` 负责单段输入和时间计划；`auto_director.py` 负责生成状态与复用协调；`foot_contact.py`、`seam_smoothing.py`、`split_seam.py` 分别处理脚接触和接缝；`finishing.py` 负责独立道具动作与只读诊断。Action 读取统一经过 `utils.iter_action_fcurves`。保留旧调用入口和场景属性，旧工程可继续打开。

源码不包含角色、场景、第三方插件或账号设置。测试应在 Blender `--background --factory-startup` 中执行，真实工程回归只使用内存副本。

## 构建与验证

运行 `python tools/build_latest.py` 生成最新 ZIP 与 SHA256 清单，工作区内默认输出到 `D:\Agent Workspaces\Agent Delivery\BA_Animation_Workflow\releases\<版本>`。可用 `--output-dir` 指定测试输出目录；独立克隆仓库仍默认输出到仓库的 `dist`。详细使用见 `docs/BA_ANIMATION_WORKFLOW_GUIDE.md`，验证记录见 `docs/VALIDATION_0.10.0.md`。不再使用旧整套配置安装器。

工作区配置备份位于 `D:\Agent Workspaces\Agent Temp\BA_Animation_Workflow\backups`；测试输出应放在同一任务临时目录下。`dependencies` 保留本工具历史集成所需的桥接与第三方安装包，不作为上游开发主库。
