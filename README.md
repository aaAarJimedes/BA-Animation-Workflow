# BA Animation Workflow

Blender 5.1 的单段动作制作、复用和收尾工具。当前版本 **0.10.0**。

## 使用

安装 `ba_animation_workflow-0.10.0.zip`，在 `N → BA 动画` 中选择角色。生成依赖独立安装的 Proscenium 与 Proscenium Motion Bridge；两者不包含在本包内。

- 一个 Clip 对应一个动作提示。编辑器只粘贴英文动作内容，帧数在面板设置。YAML、Markdown 包装和关键帧说明会明确报错，避免把整份制作方案当成动作提交。
- 面板显示 `N/1000` 字符及按场景真实 FPS 计算的时长。插件不会为匹配示例擅自更改场景帧率。
- 动作复用保留文本和源 Action 的可靠关联、防脚滑、单侧/前后均分接缝，以及重复操作和失败恢复保护。修改较早的均分接缝前，需从后向前撤回相连修正，避免破坏后段或人工修改。

## 道具接触与动作检查

在子面板选择角色、道具、持握骨骼和帧范围。先在开始帧将道具摆进手中，再烘焙持握。工具按照已有手部动作生成独立的道具 Action，在放下帧以后保持释放位置；原角色动作不会被改动。恢复按钮撤回本工具的道具 Action。

道具应是本场景中可编辑、无父级、无约束、无动画的独立对象。工具不会自动修改手的接触位置；应先修好手的抓取/放下动作。双手道具需要人工保证第二只手的握点。

“检查停顿与速度”只采样手和头部，输出低速区间及峰值帧的文本报告。它不自动删帧，低速候选也不等同于错误；有意停留和接触姿态应保留。

## 开发结构

`extension/ba_animation_workflow/clip_plan.py` 负责单段输入和时间计划；`auto_director.py` 负责生成状态与复用协调；`foot_contact.py`、`seam_smoothing.py`、`split_seam.py` 分别处理脚接触和接缝；`finishing.py` 负责独立道具动作与只读诊断。Action 读取统一经过 `utils.iter_action_fcurves`。保留旧调用入口和场景属性，旧工程可继续打开。

源码不包含角色、场景、第三方插件或账号设置。测试应在 Blender `--background --factory-startup` 中执行，真实工程回归只使用内存副本。

## 构建与验证

运行 `python tools/build_latest.py` 生成最新 ZIP 与 SHA256 清单。详细使用见 `docs/BA_ANIMATION_WORKFLOW_GUIDE.md`，验证记录见 `docs/VALIDATION_0.10.0.md`。不再使用旧整套配置安装器。
