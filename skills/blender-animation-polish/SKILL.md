---
name: blender-animation-polish
description: Refine an existing Blender character animation into a reviewable scene with natural transitions, meaningful gestures, prop contact, preserved animation during MMD model replacement, camera staging, adjustable toon looks, and verified delivery. Use for polishing imported/generated/stitched motion or developing reusable toon tools in an existing project; not for text-only motion prompts or creating a film from scratch.
---

# Blender 动画完善工作流

把已有模型、场景和生成/拼接动作完善成可检查、可继续编辑的工程。先保住已经成立的动作与用户认可的效果，再修复具体缺陷。只进入本次请求需要的分支；单独调卡渲不重新生成动作，单独修衔接不重新导入模型。

## 建立本轮工作契约

从当前工程与最新反馈确认：输入/输出文件、Blender 版本、有效 FPS（fps / fps_base）、正式出片范围、负帧预热及缓存状态、角色/骨骼/表情绑定、实际相机、必须保留的动作、允许修改的部位/区间，以及视觉参考。把未知项和重要判断写进任务记录；已有数据足够时直接推进，不重复索要已授予的权限。

为原始工程保留可恢复副本，给本轮修订使用独立路径。用户指定回退版本时，以该版本重建本轮基线；不要按版本号最大或修改时间最新选择被否决的动作。用户可能同时编辑：落盘前核对最新文件和内存状态；有新保存就比较语义变化，合入本轮已验证的局部修订。文件哈希不同不等于动作不同，当前帧改变也会改文件字节。

可用 [scripts/audit_scene.py](scripts/audit_scene.py) 在 Blender 中生成只读基线，比较方法见 [references/verification.md](references/verification.md)。本工具记录状态，不判断画面自然度，也不证明物理已正确烘焙。

## 不随优化丢失的条件

- 保持项目现有 FPS。需要压缩停顿时调整动作时间映射；同步物体、骨骼、表情、相机数据、NLA 和标记，避免共享 Action 重复变换。帧率变更只在任务明确需要时进行。
- 分别记录正式输出、动作关键帧、时间轴预览和物理缓存范围。负帧必须有实际起始姿态/过渡；显示出负帧不代表存在预热动画，更不代表已烘焙。
- 先列出“必须保留的动作节点”：抓握、释放、接触次数、拍手、整理衣服、支撑脚、转身、最终姿势等。曲线更平滑但动作消失，属于回归。
- 小幅衣物交叠是否可接受由工程和用户要求决定。不要为了零碰撞把肘和手持续向前、向外推开。严重手掌/指尖消失、手腕扭折、道具漂浮才是优先处理的问题。
- 数值检查筛出可疑帧，实际相机画面和连续播放判定效果。辅助特写相机通过，不能代替正式相机验收。

## 按需执行

1. **动作规划与衔接**：读 [references/motion.md](references/motion.md)。区分真实停顿与动作准备/回弹，缓存未修改的完整源姿态，局部修整并保护接触、关键动作和边界速度。
2. **人物换新或道具交互**：读 [references/model-and-contact.md](references/model-and-contact.md)。先判断骨架是否真正兼容；优先沿用已验证的动画骨架并替换网格/材质。按抓握→受支撑放置→释放的真实接触状态设计道具运动。
3. **镜头与卡渲**：读 [references/camera-and-toon.md](references/camera-and-toon.md)。用同机位、同帧对照定位发白/过饱和来源，再分别调环境显示、人物明暗、阴影、描边。允许不同工程选不同方法。
4. **MMD 物理、头发或重新烘焙**：读 [references/physics.md](references/physics.md)。区分模拟缓存、视觉骨骼烘焙和烘焙后修饰；保护源动作与负帧预热，检查第 0 帧、碰撞布局和整条发链的可动性。
5. **完整出片、断点续渲染或磁盘暴涨**：读 [references/rendering.md](references/rendering.md)。为源版本隔离片段、控制长时间进程的内存增长，完成全解码和拼接验证。静音与带音效按本轮要求分别交付。
6. **插件重构、安装或仓库发布**：仅在请求包含这些工作时读 [references/addon-and-delivery.md](references/addon-and-delivery.md)。把可复用机制沉淀为工具，并用真实 Blender 行为验证。技能本身不附带发布、付费生成或清理其他项目的授权。
7. **保存、复核与归档**：读 [references/verification.md](references/verification.md)。实际依赖打包、最终目录重开、必要清理完成后交付。只报告实际完成的检查与已知限制。

需要新的 Proscenium 动作时，优先使用可用的 `proscenium-prompt-writing` 编写单动作提示词、`proscenium` 操作实际插件；未安装这些 skill 时也遵守以下最小契约：一段 clip 是一个主动作和一次生成，只有一个可直接复制的英文提示词，手动关键帧/FPS/范围另列；当前 Proscenium 提示词上限需核对，本案例验证为 1000 字符。文本不保证接触正确；根据被接受的实际末姿衔接。相同约束连续生成仍失败时，检查约束/骨架或局部修整，避免无限重复请求。

## 工具与验收边界

Blender Python/MCP 适合检查数据、执行精确修改和后台渲染；可用的 Computer Use 适合查看真实面板、视口和播放。先识别正确的 Blender 版本、窗口和文件，再操作。用户主动中断界面控制时停止该交互，遵循当时的继续工作范围；不得把一次项目授权带到以后所有项目。原生界面能力不可用时继续可执行的后台工作，说明尚未完成的界面验收。

“生成了预览文件”“检查了连续帧”“播放看过动态”“在用户当前窗口打开”是不同事实。不要用其中一个代替其他几个。项目已验证后，只有新修改、失败或未解决的问题才触发扩大/重复检查。

本 skill 源自 Blender 5.1.2 实际工程。已验证结论、失败教训及本机源码索引见 [references/validated-case.md](references/validated-case.md)，只在需要实例/复用代码时读取。骨骼名称、毫米阈值、动作帧号、机器路径和卡渲参数均为案例值，不是新工程默认值。
