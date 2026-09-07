# AI 自然语言生成 3D 动作：Blender / MMD 调研报告

调研日期：2026-08-29  
目标环境：Windows 11、Blender 5.1.2、RTX 5080 16GB、约 47.4GB 内存  
目标工作流：《蔚蓝档案》风格 MMD 角色动画，现有 BlendCap + BlendCap Motion Bridge + MMD Tools

## 一页结论

目前已经有能把自然语言变成可编辑骨架动作的产品，但它们更适合产生“身体动作底稿”，还不能一句话包办 MMD 成片。手指、表情、头发裙摆、枪械握持、双手接触、脚底锁定和二次元夸张仍需要后续修复。

针对本机与现有工作流，推荐顺序是：

1. **先做零部署云端基准：Animatica Proscenium 与 Uthana。** 两者都有 Blender 内工作流；前者基于 NVIDIA Kimodo，并提供关键姿势、根路径和手脚约束，后者把生成、预览、重定向、裁剪/拼接和导入放在同一产品链中。它们最适合验证“文本生成究竟能否比 BlendCap 或手工 K 帧省时间”。
2. **用 QuickMagic、Rokoko Create 或 DeepMotion SayMotion 做浏览器对照组。** 它们安装成本低，FBX/BVH 能进入现有 MMD 重定向链。QuickMagic 明确面向多语言和 MMD 工作流，但当前 Text-to-Motion 是否直接提供 VMD 需要在账号界面实测，不能仅凭其视频动捕产品的 VMD 支持推断。
3. **长期本地首选 NVIDIA Kimodo，只安装一套 Blender 桥接。** 官方模型的文本编码器放到 CPU 后，显存可从约 17GB 降到 3GB 以下；这使 RTX 5080 16GB 具备现实可行性。社区 `kimodo_motion` 明确面向 MMD/VRoid/Mixamo，Kimodo Blender Bridge 和 Animatica 的控制能力则更完整。
4. **暂不把 HY-Motion 作为主线。** 腾讯官方给出的最低显存约为 Lite 24GB、标准版 26GB；第三方插件宣称 8GB 可运行，属于量化/卸载后的厂商方案，需独立验证，不能视为官方硬件结论。
5. **ARDY 与传统研究模型仅列观察/R&D。** ARDY 很有潜力，但 SOMA 模型与 Blender 桥接尚不成熟；MDM、MotionGPT、MoMask 等多数输出 22 关节坐标或研究格式，不是新手可直接编辑的 MMD Action。

综合判断：**第一轮只测 Animatica、Uthana、QuickMagic/SayMotion 各一个云端候选；质量收益成立后，再在隔离环境部署一套 Kimodo 本地桥接。不要同时安装多个 Kimodo 包装器。**

## 1. 调研口径

本报告把“文本生成动作”限定为：

> 输入描述动作语义的自然语言，模型合成一段新的、随时间变化的 3D 人体骨架运动，并能以 Blender Action、FBX、BVH、GLB、NPZ 等形式继续编辑或重定向。

以下能力不等同于 Text-to-Motion：

- LLM 根据提示编写 Blender Python，再用规则给骨骼打关键帧；
- 用自然语言搜索现成动作库；
- 自动绑骨后套用预设动作；
- 视频/摄像头动捕；
- AI 补间、物理修复、脚锁和曲线清理。

这些邻接工具仍可能有用，但如果混入主表，会让“真的生成新动作”和“自动调用旧动作”难以区分。

## 2. 推荐梯队

### P0：立即值得做 A/B 测试

| 方案 | 运行方式 | 进入 Blender 的路径 | 突出能力 | 关键限制 | 对本项目的判断 |
|---|---|---|---|---|---|
| [Animatica Proscenium](https://animatica.ai/kimodo) | Blender 插件；云端或本地 Kimodo | 直接创建 Action/关键帧；Blender 5.0+ | 关键姿势、Bezier 根路径、手脚 pin、多段约束、接受/拒绝生成结果 | 新产品；提示词以英文最稳；云端涉及账号/素材上传 | **最适合验证“可导演性”**，优先用中性代理骨架试云端版 |
| [Uthana Blender Plugin](https://github.com/Uthana/uthana-blender-plugin) | 官方 Blender 插件；云端 | 生成、预览、下载、自动绑骨/重定向，FBX/GLB | 一次生成多个候选，网页可裁剪、变速、循环和混合；Blender 4.0+ | 需要联网/API key；免费结果与商用许可受套餐限制；中文未承诺 | **最接近一站式云端工具**，适合新手流程基准 |
| [NVIDIA Kimodo](https://github.com/nv-tlabs/kimodo) + 一套 Blender 桥接 | 本地 GPU/CPU 混合 | 桥接器直接生成 Action，或导出 SOMA BVH/NPZ 后重定向 | 文本、全身关键姿势、手脚位置/旋转、根路径等联合约束 | 需 25–50GB 左右环境/模型空间；Windows 桥接是社区生态；许可分层 | **本地长期首选**，但应在云端验证价值后再部署 |
| [QuickMagic Text to Motion](https://www.quickmagic.ai/tools/text-to-motion) | 浏览器云端 | 当前可靠路径按 FBX/BVH → BlendCap Motion Bridge/MMD Tools 设计 | 多语言提示、Prompt Refine、每项目多个候选，明确提到 MMD/VTuber 工作流 | Open Beta；最长约 10 秒；重定向和接触修复仍分离 | **很适合中文/MMD 对照测试**；Text-to-Motion 的 VMD 导出必须实测确认 |
| [DeepMotion SayMotion](https://www.deepmotion.com/saymotion) | 浏览器云端 | FBX、GLB、BVH → Blender/MMD 重定向 | 局部重生成、合并、延长、循环、脚锁/平滑、自定义角色 | Open Beta；全身为主，无可靠手指/面部；免费下载额度低 | **稳定的网页质量基准**，不要求先装插件 |

### P1：有真实能力，但需验证明显疑点

| 方案 | 优点 | 疑点/成本 | 建议 |
|---|---|---|---|
| [Kimodo Blender Bridge](https://github.com/lewdineer/Kimodo_Blender_Bridge) | Blender 4.0+，明确测试 5.1；多提示词、多个变体、骨名模糊映射、路径与身体约束，能 Bake 到任意 humanoid | 第三方社区桥接，不是 NVIDIA 官方插件；其低显存说法依赖自身量化/卸载实现 | 与 `kimodo_motion` 二选一；先在隔离配置验证注册、卸载、Action 输出和 MMD 重定向 |
| [Kimodo Motion](https://github.com/atticus-lv/kimodo_motion) | Blender 5.0.1+；明确列出 MMD、VRoid、Mixamo、自定义人形；本地 Action/NLA；可选中文翻译 | 社区成熟度低，Windows 一键运行时与上游模型需要共同审计 | 若“中文 + MMD 直达”优先，首测它；不要和其他 Kimodo 包装器并装 |
| [Rokoko Create](https://www.rokoko.com/products/studio/rokoko-create) | 浏览器文本生成，Studio 内可平滑、裁剪、循环、合并，FBX/BVH 导出；生态完整 | 不在 Blender 内生成；历史文档将其标为实验性短动作，手指数据现状需实测 | 适合走、跑、待机、挥手等基础动作对照，不作为精确武器动作主工具 |
| [Higgsfield Blender Plugin](https://higgsfield.ai/plugins/blender) | Blender 内提示词直接落关键帧，支持 Blender 4.2–5.1，原生交互新 | 2026-08 新发布；尚无充分证据证明可低成本作用于已有 MMD armature，精确接触/路径控制未披露 | 用无版权代理角色做 1 次短测；先查生成 rig 结构和动作转移成本 |
| [Motion Gen](https://haseebahmed295.github.io/motion_gen/)（HY-Motion） | 本地 Blender 插件，内置 SMPL-X，输出可 Bake；宣称混合卸载可支持较低显存 | 上游 [HY-Motion](https://github.com/Tencent-Hunyuan/HY-Motion-1.0) 官方最低 24–26GB；自定义角色无内建重定向，文档建议另购 Auto-Rig Pro；英文提示 | 只做实验，不作为稳定环境；必须以 16GB 实测峰值和失败回滚为准 |
| [Text2Motion Blender Integration](https://github.com/text2motion/blender-integration) | Blender 内输入提示、时长和 root motion | Early Preview；只支持严格 Mixamo 命名与 GLB，FBX 明确不可用；服务当前可用性和复杂许可需复核 | 沙盒观察，不进入稳定配置 |

### P2：特定场景或低优先级

| 方案 | 适合 | 不适合 |
|---|---|---|
| [Krikey AI Text to Animation](https://www.krikey.ai/AI-Text-To-Animation) | 快速口播、教学、社交媒体 Avatar 成片，付费可导 FBX | 精细的 MMD 身体演技、根路径和道具接触控制 |
| [BlendSwap Studio Animate](https://blendswap.com/studio/animate) | 简短英文提示生成 1–10 秒 Mixamo 兼容 FBX | 直接 MMD 骨架、复杂约束、中文和深度 Blender 集成 |
| AI Animation Forge | 本地 Kimodo 的另一种商业包装，批量生成和路径约束 | 与其他 Kimodo 包装器重复，且版本/显存声明需额外核验 |

## 3. Blender 内直连方案详表

### 3.1 Animatica Proscenium

[Animatica 插件仓库](https://github.com/animatica-ai/animatica-blender-plugin)当前面向 Blender 5.0+。它的优势不是只提供一个提示框，而是允许把语言与关键姿势、Root 曲线、手脚 pin 组合起来；这比完全随机地抽动作更接近动画师的“导演控制”。云端版还能把动作重定向到任意 humanoid，接受结果后再 Bake 成普通关键帧。

它非常适合《蔚蓝档案》动作的原因是：角色化表演常需要明确的开始剪影、重心移动、停顿和结束姿势。单靠“可爱地挥手”很不稳定，而“固定开始/结束姿势 + 手部目标 + 文字描述”更可能减少清理。

建议先用托管免费额度，不下载本地模型。只上传中性代理 rig；验证节省时间后再考虑本地 Kimodo。

### 3.2 Uthana

[Uthana Text-to-Motion](https://uthana.com/product/text-to-motion)提供多个生成候选，并把预览、剪辑、速度、循环、混合、下载和角色重定向串在一起；官方插件支持 Blender 4.0+。按量页面在本次调研时列出不同模型大约每生成秒 0.02、0.03、0.10 美元，但定价区块有新旧内容并存，购买前必须以结账页为准。[Uthana 定价](https://uthana.com/pricing)

优点是集成完整，缺点是云端依赖。免费档可用于非商用试验，但正式发布前应再次核对当前套餐和输出许可。不要把 API key 保存在 `.blend` 或项目 manifest 中。

### 3.3 Kimodo 两类社区桥接

目前至少有两条值得关注的社区路线：

- `Kimodo Blender Bridge`：控制项和路径能力更丰富，适合英文提示、精确路径与通用 humanoid；
- `kimodo_motion`：更明确强调 MMD/VRoid/Mixamo、自定义骨架、NLA 和可选中文翻译，适合本项目快速接线。

两者都只是桥接 NVIDIA 模型，不代表 NVIDIA 官方支持。应只选一个做试验，否则可能重复保存模型、Python 环境和缓存，占用数十 GB，并制造 CUDA/Python 依赖冲突。

## 4. 云端/浏览器方案详表

### 4.1 QuickMagic

[QuickMagic Text to Motion](https://www.quickmagic.ai/tools/text-to-motion)在 2026-06-05 进入 Open Beta：自然语言生成可编辑骨架动作，支持多语言、提示优化、最长约 10 秒，并可在一个项目比较多个候选。官方说明明确承认重定向、Root、循环、脚滑和接触仍需制作端清理。

当前有一个容易误读的格式问题：其[价格页](https://www.quickmagic.ai/Pricing/)中，通用 Motion Studio/视频动捕格式表包含 VMD；但单独的 Text-to-Motion 格式表当前列的是 FBX、BIP、C4D、BVH、Unreal、Mixamo、Unity Anim、CC/iClone，未列 VMD。产品页虽提到 MMD 工作流，也不等于当前账户一定能以 VMD 导出文本生成结果。因此首测按 **FBX/BVH → 现有 MMD 重定向** 设计；若界面实际提供 VMD，再把它作为额外直达路径验证骨名、IK、Root 和帧率。

免费档不含商用许可，资产保留期约 15 天；付费 Basic 及以上页面标注商用。重要动作必须及时下载，云端不能当永久资产库。

### 4.2 Rokoko Create

[Rokoko Create](https://www.rokoko.com/products/studio/rokoko-create)把文本生成与原有 Studio 编辑/导出结合，适合作为新手友好的基础动作库生成器。官方提示建议短、具体的动作；生成后可做平滑、裁剪、循环和混合，再导出 FBX/BVH。[Rokoko 定价](https://www.rokoko.com/pricing)当前免费档包含文本生成和有限 Studio 导入，付费档提高导入和导出能力。

它适合待机、走跑、转身、挥手；椅子、墙面、枪械等外部接触以及精确轨迹仍要保守看待。官方不同年代页面对手指能力表述有变化，生产测试应暂按“身体为主”评分。

### 4.3 DeepMotion SayMotion

[SayMotion 文档](https://www.deepmotion.com/doc/saymotion)确认它是真正的网页文本到全身动作，并支持局部重生成、合并、延长和循环；输出 FBX、GLB、BVH、MP4，也能把结果应用到自定义 FBX/GLB/VRM 角色。它没有原生 Blender 生成面板，但现有 MMD 重定向链足以承接 FBX/BVH。

本次查看的[动态价格页](https://www.deepmotion.com/pricing-saymotion)显示免费额度很少，付费档按年付折算约从 9 美元/月起。它仍标 Open Beta，且文档明确以全身动作为主，手指和面部不是当前强项。

## 5. 本地开源模型

| 模型 | 能力/输出 | 本机适配性 | 生产判断 |
|---|---|---|---|
| [NVIDIA Kimodo](https://research.nvidia.com/labs/sil/projects/kimodo/) | 文本 + 姿势/手脚/路径约束；SOMA、SMPL-X、G1；NPZ，可转 SOMA BVH | 全 GPU 约 17GB；文本编码器放 CPU 后官方称低于 3GB；RTX 5080 16GB 可行 | **唯一值得优先产品化的本地模型** |
| [NVIDIA ARDY](https://github.com/nv-tlabs/ardy) | 实时、自回归、长时流式动作，运行中可改提示和约束；NPZ | 官方主要测试 Ubuntu/RTX 4090；SOMA 模型仍为 coming soon；无成熟 Blender/MMD 接口 | 观察名单 |
| [Tencent HY-Motion 1.0](https://github.com/Tencent-Hunyuan/HY-Motion-1.0) | 1B / 0.46B Lite，文本到 3D 全身动作 | 官方最低约 26GB/24GB，超过本机 16GB；英文提示较稳；自定义许可有地域和用途条款 | 不作为本机稳定主线 |
| [MoMask](https://github.com/EricGuo5513/momask-codes) | HumanML3D 22 关节；NPY、MP4、BVH；提供 Blender/重定向说明 | 可 CPU 运行，部署较轻；原始依赖老，BVH 足部 IK 偶尔失败 | 传统模型中的轻量备用 |
| [MDM](https://github.com/GuyTevet/motion-diffusion-model) | 文本生成、补间和编辑；22 关节坐标/SMPL | PyTorch 1.x/CUDA 11 老环境，无原生 BVH/FBX | 研究基线，不适合新手主线 |
| [MotionGPT](https://github.com/OpenMotionLab/MotionGPT) / [MotionGPT3](https://github.com/OpenMotionLab/MotionGPT3) | 文本与动作多任务；22 关节 NPY，可拟合 SMPL/PLY | Blender 支持不完整，仍需格式转换和重定向工程 | R&D，不是插件 |

### Kimodo 对本机的现实意义

Kimodo 是本轮调研中最关键的新变化。其官方仓库说明，全 GPU 推理约需 17GB VRAM；把文本编码器设为 CPU 后可降到 3GB 以下，速度略慢。这比只看“推荐 24GB 显存”更符合本机 RTX 5080 16GB 的条件。

但显存数字不等于整个工作流零门槛：

- 官方开发环境以 Linux 为主，Windows 需要 Docker 或社区运行时；
- 模型、SOMA/SMPL-X、Llama 文本编码器有各自许可和获取条件；
- Blender 桥接、模糊骨名映射和 MMD 重定向都是社区层；
- 本机 ComfyUI 审计时已占约 12.7GB 显存，运行 Kimodo 前必须完全释放图像模型；
- 模型和运行时可能占 25–50GB，本机 C 盘仅余约 11.6GB，必须放在 D 盘。

如果选择 ComfyUI 路线，可使用社区 [ComfyUI-Kimodo](https://github.com/jtydhr88/ComfyUI-Kimodo)导出 NPZ、SOMA BVH 或 Mixamo FBX，再交给 MMD 适配器。但它和现有图像生成节点会争抢显存；在本项目中，独立本地服务或 Blender 桥接更符合“一站式”。

## 6. 为什么研究模型很难直接变成 MMD Action

传统 HumanML3D 系模型通常有共同边界：

- 22 关节、约 20fps、几秒到十秒的身体动作；
- 训练文本主要是英文；
- 不包含面部、手指、头发、裙摆、武器和复杂接触；
- 输出常是 `(T, 22, 3)` 关节坐标、SMPL 参数或逐帧网格，而不是 Blender Action；
- 生成分布以日常人体动作为主，夸张二次元战斗和枪械操作不是强项。

因此，一句话生成动作应被定位为：

> 用较低成本获得多个身体表演草稿，挑出最好的一条，再把人工劳动集中到重定向、接触、节奏和角色化修复。

它替代的是“从空白开始 K 全身”，不是替代动画导演、绑定修复和最终润色。

## 7. 明确排除或仅作邻接工具

| 工具 | 实际能力 | 本报告判定 |
|---|---|---|
| BlendCap、Plask、DeepMotion Animate 3D、Move AI、Rokoko Vision | 视频/摄像头 → 动捕 | 与 Text-to-Motion 是互补输入源，不是文本生成 |
| [Cascadeur](https://cascadeur.com/) | AI 姿势、补间、物理、Root Motion 和动作清理 | 很适合生成后修脚滑/重心，但不是自然语言生成器 |
| Mixamo | 动作库搜索、自动绑骨、重定向 | 非生成式文本动作 |
| [Anything World Animate Anything](https://github.com/anythingworld/animate-anything-blender) | 自动分类、绑骨和预设动画 | 不是任意动作语句生成新人体运动 |
| [Motorica](https://motorica.com/) | 生成式 locomotion、风格、根路径、运动匹配数据 | 当前无可靠证据证明其 Blender 产品支持任意自然语言动作 |
| [Kinetix](https://kinetix.tech/research-3d) | 研究层存在自然语言到全身动画模型 | 当前公开产品偏视频 emote / 游戏 SDK，未形成普通 Blender 自助流程 |
| [Blender Lab MCP Server](https://www.blender.org/lab/mcp-server/) | LLM 控制 Blender Python，可规则化创建关键帧、镜头和灯光 | 不是学习式人体运动模型；执行生成代码还有安全边界 |

## 8. 建议的一站式接入架构

```text
中文动作意图
  ↓
结构化动作提示（保存中文原文 + 规范英文）
  ↓
Provider：Animatica / Uthana / QuickMagic / Kimodo Local
  ↓
中性源骨架 + RAW_AI Action（永不覆盖）
  ↓
现有 BlendCap Motion Bridge / MMD Tools 重定向
  ↓
RETARGET Action
  ↓
CLEAN：Root、脚锁、抖动、穿地、关键帧精简
  ↓
CORR：手指、表情、武器接触、剪影与二次元节奏
  ↓
NLA 编排、镜头、灯光、渲染
```

建议把未来的 BA Animation Workflow 扩展为 Provider 适配层，而不是把某一家服务写死：

- `Generate`：向服务或本地模型提交规范提示；
- `Import as RAW`：总是创建新 Action，不覆盖当前 Action；
- `Retarget`：调用现有角色映射；
- `Validate`：检查帧率、Root、左右脚、NaN、骨架映射和动作范围；
- `Promote to CLEAN`：复制后再清理；
- `Record provenance`：记录模型、版本、提示词、seed、时长、导出格式、许可套餐和源文件哈希。

建议命名：

```text
ACT_<角色>_<动作>_AI_RAW_<Provider>_<Seed>
ACT_<角色>_<动作>_RETARGET
ACT_<角色>_<动作>_CLEAN
ACT_<角色>_<动作>_CORR
```

## 9. 提示词写法

模型更容易理解可观察的身体行为，不容易理解只含审美词的要求。推荐模板：

```text
[主体与起始姿势]
+ [依次发生的动作]
+ [左右、方向、速度、力度]
+ [Root 路径或原地要求]
+ [停顿/接触]
+ [结束姿势]
+ [时长]
```

中文意图：

```text
少女从低位警戒姿势开始，向前快走两步，双手举枪瞄准左前方，
停一秒，再回到平衡站姿；总长 5 秒。
```

规范英文：

```text
A young woman starts in a low ready stance, takes two quick steps forward,
raises a rifle with both hands and aims to the front-left, holds for one second,
then returns to a balanced standing pose. Duration: 5 seconds.
```

需要注意：模型可以生成“像是在握枪”的身体动作，却不知道实际枪托、握把和角色手掌的准确几何关系。双手与武器接触仍应在 `CONTACT_FIX/CORR` 层处理。

## 10. 首轮统一基准测试

### 候选

- Animatica Proscenium 云端；
- Uthana；
- QuickMagic 或 SayMotion（二选一浏览器基准）；
- 质量收益成立后，再测一套本地 Kimodo 桥接。

### 固定动作集

每项 4–6 秒、30fps、每个候选生成 3 个 seed：

1. 待机呼吸，重心缓慢从左脚换到右脚；
2. 向前走四步，停止，向左转身并挥右手两次；
3. 从椅子上起身，站稳后整理衣服；
4. 向右侧快速闪避，低姿势停顿，再恢复警戒；
5. 双手举起代理长枪，瞄准左前方一秒后放下。

第三、第五项刻意测试环境/道具接触；它们很可能失败，但能最快暴露产品演示之外的实际边界。

### 评分（分析框架，不是厂商评分）

| 指标 | 权重 | 记录方法 |
|---|---:|---|
| 提示遵从 | 25 | 动作顺序、左右、方向、速度、结束姿态 |
| Root 与脚底 | 20 | 根轨迹、转向、累计脚滑、穿地 |
| MMD 重定向 | 20 | 映射错误数、肩肘膝扭曲、导入/重定向分钟数 |
| 可编辑性 | 15 | 是否为普通 Action、关键帧密度、能否分层/循环/拼接 |
| 人工修复成本 | 15 | 从 RAW 到可用 CLEAN/CORR 的分钟数 |
| 成本与许可 | 5 | 单次费用、下载限制、商用许可和资产留存 |

### 晋级条件

- 3 个 seed 至少有 1 个动作顺序和左右方向正确；
- 导入后为普通可复制 Action，且不要求永久绑定某个在线插件；
- 不破坏原始 MMD Action 和角色文件；
- 与“BlendCap 拍一遍 + 修复”或手工块动画相比，中位数人工时间至少下降约 40%；
- 许可与缓存位置能够被记录和复现。

任一方案若连续两个基准动作出现不可修复的 Root 翻转、骨架错配，或导出必须上传正式角色且不能删除，则停止评估。

## 11. 安装、权限与清理策略

本报告是调研，不在本轮安装任何候选。后续试装应遵守：

1. 只在 Blender 5.1 `lab` 配置或独立便携配置安装，先记录扩展 ZIP、来源、版本、SHA-256 和权限。
2. 本地模型、venv、Hugging Face 缓存统一放到 D 盘的独立目录；C 盘余量不足，禁止默认下载几十 GB 模型。
3. 不把 PyTorch/CUDA 依赖直接装进 Blender 5.1 内置 Python；优先插件独立运行时、本地服务或独立 venv。
4. 试 Kimodo 前关闭 ComfyUI 并确认显存释放；生成和渲染不要并行争抢 16GB VRAM。
5. 云端首测只用中性代理骨架，不上传原始《蔚蓝档案》角色。API key 放系统凭据/环境配置，不写入 `.blend`、日志或版本库。
6. 每轮测试只保留：安装包与哈希、成功运行时、模型版本、源导出、提示/seed、测试表和通过的 RAW Action。
7. 失败的虚拟环境、下载中断文件、临时预览和重复模型缓存先移动到项目 `_trash`，经清单确认后删除；不递归清理 AppData、全局缓存或其他 Blender 版本。
8. 卸载测试必须验证：插件禁用、注销、重启 Blender 无报错，既有 `.blend` 仍能打开，已 Bake 的普通 Action 不依赖插件继续存在。

## 12. 最终建议

短期不要把“AI 文本动作”当成 BlendCap 的替代品，而应把两者作为两个输入 Provider：

- 有演员或能自拍：BlendCap 通常更忠实，适合精确时序和表演；
- 没有演员、想快速探索：Text-to-Motion 更适合待机、走跑、转身、姿势过渡和动作创意；
- 有精确道具/接触：关键姿势/路径约束的 Kimodo 系最有希望，但仍需 CONTACT_FIX；
- 手指、脸和二次元角色化：继续交给现有 MMD 表情、姿势资产和人工 CORR 层。

推荐决策：**先测 Animatica + Uthana + 一个浏览器服务，记录修复分钟数；只要 Kimodo 系在五项基准中达到 40% 以上净省时，再部署本地单一桥接并接入 BA Animation Workflow。** 这能在不污染现有稳定环境的前提下，最快判断 AI 动作是不是“演示好看”，还是确实能提升个人生产效率。

## 主要来源

- [NVIDIA Kimodo 官方仓库](https://github.com/nv-tlabs/kimodo) / [项目页](https://research.nvidia.com/labs/sil/projects/kimodo/)
- [Animatica Proscenium](https://animatica.ai/kimodo) / [Blender 插件](https://github.com/animatica-ai/animatica-blender-plugin)
- [Uthana Text-to-Motion](https://uthana.com/product/text-to-motion) / [Blender 插件](https://github.com/Uthana/uthana-blender-plugin)
- [QuickMagic Text to Motion](https://www.quickmagic.ai/tools/text-to-motion) / [价格与格式](https://www.quickmagic.ai/Pricing/)
- [Rokoko Text-to-Motion 说明](https://support.rokoko.com/hc/en-us/articles/48797362745489-Generating-Motion-from-a-Text-Prompt) / [导出格式](https://support.rokoko.com/hc/en-us/articles/18877624744721-Rokoko-Studio-Export-options-and-file-formats)
- [DeepMotion SayMotion](https://www.deepmotion.com/saymotion) / [文档](https://www.deepmotion.com/doc/saymotion)
- [Tencent HY-Motion 1.0](https://github.com/Tencent-Hunyuan/HY-Motion-1.0)
- [NVIDIA ARDY](https://github.com/nv-tlabs/ardy)
- [MoMask](https://github.com/EricGuo5513/momask-codes)
- [MDM](https://github.com/GuyTevet/motion-diffusion-model)
- [MotionGPT](https://github.com/OpenMotionLab/MotionGPT)

价格、免费额度、版本和服务状态都可能变化；本报告的数字只代表 2026-08-29 官方页面所示状态，安装或付费前应复核实时页面。
