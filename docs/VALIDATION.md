# 验证记录

## BA Animation Workflow 0.9.0：前后均分与成对恢复

- 默认仍为「仅当前段」；新增均分总窗口，偶数均分，奇数给当前段多 1 帧。用位置 Hermite 和旋转球面曲线连接两侧；只修改窗口内共同骨骼通道，两段边界姿态一致。
- 配对备份前段和当前段原版；重新映射前撤回原前段尾部修正。重复、10→11 帧、切回单侧、关闭恢复、注入失败回滚、人工修改拒绝恢复测试通过。前段之外及当前段窗口之外的关键帧与手柄保持不变。
- 真实第八→九段（边界 668）测试，10 帧窗口 663–673；边界位置误差 0，旋转点积误差小于 1e-7；重复计算最大数值差约 6e-7。修正了微小速度四元数 acos 精度导致重复计算漂移的问题，改用 atan2。
- 新模型两段导入与关闭恢复通过，来源模型不变；原单侧回归及自动导演 smoke 通过。测试不保存用户工程，不请求云生成。
- 保护条件：手改接缝、缺失配对备份、其他模型共用 Action、窗口重叠时拒绝；重映射已有后续均分接缝的前段时，要求先在后一段关闭并映射，避免留下半个旧接缝。
- 安装版 0.9.0 的配对回归和新模型导入均通过；真实第八→九段单帧角速度差约 6.307° → 1.862°（均分仍保留自然加速度，并非强制每帧恒速）。安装备份 `backups/profile-production-20260907-000958-216`。ZIP 61,722 B，SHA-256 `229d4cd1d751414827a16443e3d0b29495b38e18754c641efdd8bfbf54643824`。

## BA Animation Workflow 0.8.9：复用限定实验防接缝突变

- 第九段 668 帧接缝复现约 6.3067° 的单帧角速度差，原连续性只对齐姿态。新功能默认关闭，首两帧承接前段位置/旋转速度，默认 10 帧窗口平滑回归本段；只在复用两个入口调用。
- `seam_smoothing_reuse_test`：第九段开关前最大角速度差 6.3067°，开启后低于浮点测量精度；姿态/位移速度对齐；前后其他片段关键帧不变，窗口后关键帧及手柄完全不变，关闭后重新映射恢复基准。
- `seam_smoothing_import_test`：新模型首个导入片段无前段时跳过，连续第二段生效；短段跳过，旧模型及前段不变。自动导演 smoke 通过。
- 最新真实工程开启了 MMD 腿部 LIMIT_ROTATION 覆盖，防脚滑安全检查会拒绝，未修改该检查或原工程约束。双实验组合在后台临时 FK 测试配置（仅内存静音 MMD 限制）验证通过；组合在开头窗口优先平滑，可能放松脚锁定。
- 所有测试均后台进行，不保存用户工程、不请求云生成。
- 0.8.9 已安装并通过安装版的接缝 A/B、新模型导入与 profile smoke。备份 `backups/profile-production-20260906-235456-311`。ZIP 57,287 B，SHA-256 `fec2c1a5e2ac87739119fc8f5b92b7935d2a8e3648b68e331727c4a3b8cb8370`。

## BA Animation Workflow 0.8.8：防脚滑膝盖弯曲平面修复

- 复现第九段旧版防脚滑在第 704 帧为左膝引入约 29° 额外侧向旋转。原实现将原膝位置投影到新脚目标轴，改变了腿的弯曲平面，再分别最短旋转大腿/小腿，导致侧弯和扭转。
- 改为从原髋—踝轴获取弯曲平面，整体旋转到新目标轴后在同一平面内屈膝。接近伸直时用 MMD 膝局部铰链轴确定方向，保留 1° 最小几何弯曲，避免伸直奇点；已经到位的脚不求解。
- 第九段修复后最大额外非 X 轴膝旋转 0.828°，弯曲平面点积最小 0.99999984；腿段长度误差小于 1.5e-6，脚朝向不变。合成伸直腿在 ±1e-6 扰动下弯曲方向稳定，不可达目标不会拉伸。
- 第八段脚踝稳定区间最大点间距离：左 0.16214 → 0.00377、右 0.15946 → 0.00426；首帧、其他片段关键帧、关闭后恢复回归通过。未改变防脚滑的复用限定范围，未保存用户工程。
- 已安装 0.8.8，仅替换 BA 插件；安装版第九段膝盖回归、开关 A/B 和新模型导入通过。备份 `backups/profile-production-20260906-233027-780`。ZIP 54,195 B，SHA-256 `13b427f42bde255add4727f7d921603448416633a8889add574f320b6ac88752`。

## BA Animation Workflow 0.8.7：复用限定实验防脚滑

- 新增默认关闭的 reuse_foot_contact，只在 `_import_linked_action` 与 `auto_remap_existing` 接入；自动生成的两条接受/映射路径不调用实验模块。
- Kitchen_Conservatory 第八段（594–668）A/B：排除首尾过渡后，脚踝最大点间距离左 0.16214 → 0.00374，右 0.15946 → 0.00423 场景单位，降低约 97%；首帧误差小于 1e-6。腿长限制留下约 0.00423 的最大目标残差，没有以缩放骨骼强行达标。
- 第九段：右脚支撑区间 668–694、711–742；中间抬脚区间的腿链局部旋转与关闭版本相同。
- 真实单段导入新模型、开→关重新映射恢复、非当前段关键帧保护、静止/抬高/行走/慢移接触检测测试通过；测试均为后台内存操作，不保存工程、不请求云生成。
- 已安装 0.8.7，仅更新 BA；安装版的第八段 A/B 与新模型导入回归通过。安装备份 `backups/profile-production-20260906-232024-507`。ZIP 53,815 B，SHA-256 `c59caeba56d91a72ecfcaa8aff5024d641bec992fdc0164bd913b62273c0ba1f`。

## 2026-09-06：BA Animation Workflow 0.8.6 第五段倾斜与选择同步

- 清理扩展和测试目录 Python 缓存；旧 smoke_runs 已完整归档到 backups/test-artifacts-before-086.zip。未删除用户工程、源动作、源码或安装备份。
- 真实 Kitchen_Conservatory 工程复现：旧根骨全矩阵衔接把上一段的俯仰/侧倾误作整段放置旋转。现在只持续保留世界竖直轴朝向与位置，其他根姿态差随首帧短过渡释放。
- 第五段 342–446 帧本地重新映射回归通过：首帧局部矩阵误差 2.98e-7；过渡后新增倾斜向量误差 4.77e-7；前四段原关键帧与抽样可见姿态不变。
- 已在实际 Proscenium 注册环境验证：选择第三段/第五段同步 Action、提示词块、起始帧，来回切换不改变原有动作；选择时不会替换或删除旧 Action。支持重复生成的 .001/.002 源名称；v4 关联以 Text 稳定 ID 为准，旧版仍先校验源提示词，复制文本的重复 ID 分离。
- 测试只在后台内存进行，没有保存用户工程，没有调用云端生成。已有第五段需用新版「重新映射」应用修复，无须重新生成。
- 发布包 49,626 B，SHA-256 `0244e908bca0163efdcaf3ee96b8ffdc689573a1adbda84943bbfc1537223290`。已仅更新 BA 插件至 0.8.6，配置 smoke 与安装版真实工程回归均 PASS；安装备份 `backups/profile-production-20260906-214738-556`。

## 2026-09-06：BA Animation Workflow 0.8.5 第三段误覆盖修复

- 确认第三段 Action 数据并未删除；旧版把“第四段”Text 中污染的目标映射无条件加入替换集合，导致 `224–293` 的第三段 NLA 条带被改指向 `293–342` 的第四段 Action。
- 覆盖前现在必须同时满足：BA 有效输出、同一目标模型、真实源提示词属于同一 Text。污染映射不再具有删除或替换权。
- 新增 BA 自有 NLA 条带修复：载入工程时若条带 Action 帧段与条带记录帧段不一致，只从同目标、同帧段且源提示词/文本一致的唯一 Action 中恢复；用户 NLA 与无法唯一判断的条带不改动。
- 真实 `Kitchen_Conservatory.blend` 只读载入后，第三段条带已从错误第四段 Action 恢复到原 `224–293` Action；随后本地重新映射第四段，第三段引用保持不变，第四段仍为 `293–342`。工程未保存，未调用 Hosted Generate。
- 自动导演 smoke、真实修复/重映射回归及源码/ZIP `extension validate` 均 PASS。发布包 `ba_animation_workflow-0.8.5.zip`：48,105 B，SHA-256 `b41b22a4c13e74b3145df3a0187a3b56e0e3ba43dc513323ecb15e99b27396e3`。
- 正式安装与联合 profile smoke PASS；安装版真实工程回归再次确认第三段 `224–293` 与第四段 `293–342` 同时存在且引用正确。回滚备份：`backups/profile-production-20260906-210931-670`。

## 2026-09-06：BA Animation Workflow 0.8.4 污染 Clip ID 修复

- 用户工程中的旧错误操作把“第四段”的 Clip ID 同时写进第三段输出和第三段源 Action；0.8.3 虽会在执行时重解 Text，但仍先信任 Clip ID，导致污染记录再次胜出。
- 0.8.4 将已接受源 Action 名称中的真实提示词提升为最高优先级；只要源动作存在，Clip ID 和缓存文本都不能推翻真实提示词核对。Clip ID 仅用于没有可核验源动作的兼容数据。
- 在真实 `Kitchen_Conservatory.blend` 中故意让按钮锁定被污染的第三段 Action，仍正确采用 `Proscenium_Motion: The person becomes still, turns the …` 并输出 293–342 帧第四段；293 帧接缝最大矩阵误差 `1.1920928955078125e-07`。工程未保存，未调用 Hosted Generate。
- 发布包 `ba_animation_workflow-0.8.4.zip`：47,627 B，SHA-256 `16c445baa17814080dbbf9d4eeea37706122d10804da15cc50d122d97cc92ec1`，源码与 ZIP `extension validate` 均 PASS。
- 正式安装与联合 profile smoke PASS，确认 BA Animation Workflow 0.8.4、PMB 0.9.1 及 42 个必要操作器全部可用。安装版在污染 Clip ID 的真实工程中再次正确导入第四段；回滚备份为 `backups/profile-production-20260906-205930-679`。

## 2026-09-06：BA Animation Workflow 0.8.3 旧选择绕过文本关联修复

- 在用户保存的 `Kitchen_Conservatory.blend` 中确认根因：`remap_prompt_text` 已是“第四段”，但工程仍保存了第三段 `.003` 输出作为 `remap_action`；0.8.2 的按钮把该过期 Action 名称锁定并直接传给导入，只有手动重新选择 Text 才会触发纠正。
- 0.8.3 在文件载入/插件启用时同步 Text→Action，并在每个动作复用操作真正执行时再次以 Text 为权威重新解析；按钮携带的 Action 名称仅在未选择 Text 时作为兼容回退。
- 精确回归故意让按钮锁定第三段 Action、同时保留“第四段”Text，最终仍从 `Proscenium_Motion: The person becomes still, turns the …` 输出 293–342 帧第四段到 `伊落玛丽 _arm.001`；293 帧接缝最大矩阵误差 `1.1920928955078125e-07`。工程未保存，未调用 Hosted Generate。
- 自动导演源码/ZIP smoke、真实工程回归及源码/ZIP `extension validate` 均 PASS。发布包 `ba_animation_workflow-0.8.3.zip`：47,626 B，SHA-256 `079b81148bfb88f971f21a983fd099a0b88f8cc6fc7909e7eb7d9f0c45fa99e6`，包内只有 8 个运行文件。首次安装发现扩展注册处于 Blender `_RestrictData` 上下文，访问现有 Scene 会被禁止；现已改为安全跳过即时扫描，保留正常文件载入同步，安装失败自动回滚有效。

## 2026-09-06：BA Animation Workflow 0.8.2 文本块深度关联

- 动作复用入口改为“先选文本块”：Text、已接受 Proscenium 源 Action 和角色输出 Action 共享稳定 Clip ID；Text 记录当前源动作、当前输出及按目标模型保存的输出映射。
- 同一 Text 在同一目标模型产生新输出时，新 Action 自动接管旧活动 Action / NLA 引用；旧 Action 退出复用列表，无引用时移除。不同模型的映射独立保留，避免把一个骨架的输出错误塞给另一骨架。
- 旧工程迁移不再信任单独的 `baw_prompt_text` 标签，而是交叉核对已接受源 Action 的真实提示词。真实 `Kitchen_Conservatory.blend` 中选择“第四段”直接解析到 `Proscenium_Motion: The person becomes still, turns the …`，并跳过 5 个误标为“第四段”、实际关联第三段源动作的历史输出。
- 正式安装版从“第四段”文本块直接完成 293–342 帧本地复用到 `伊落玛丽 _arm.001`；293 帧接缝最大矩阵误差 `1.1920928955078125e-07`。工程未保存，未调用 Hosted Generate。
- 自动导演深度关联回归、BA Workflow 全量 smoke、源码/ZIP `extension validate`、安装 profile smoke 均 PASS。发布包 `ba_animation_workflow-0.8.2.zip`：47,263 B，SHA-256 `0dd981c5f8f8c8d266cf3a0d2aef447d1d56945f6034550aac5d9e95fcb22bc9`，包内只有 8 个运行文件。正式安装回滚备份：`backups/profile-production-20260906-200639-170`。

## 2026-09-06：BA Animation Workflow 0.7.0 新模型动作复用

- “动作复用与重新映射”从高级设置中独立到全自动主页面，可选择任意旧模型输出 Action、关联文本和当前场景的新目标骨架。
- 新增单段导入与批量导入：单段把指定 Clip 映射为新模型活动 Action；批量按旧模型及正式帧段收集全部有效 Clip，只接受空白目标，重建首段负帧过渡、后续 NLA 条带与连续姿态。
- 新模型导入只使用旧目标 Action 作为关联索引，实际读取已接受的 Proscenium 源 Action；首段过渡从新模型自身当前/Rest 姿态开始，完全不读取旧模型已损坏的骨骼结果。旧模型、旧 Action 与旧 NLA 均不修改。
- 兼容 Motion Bridge 的目标切换保护：通过其 KEEP 安全路径临时处理恢复点，操作后还原用户原桥接会话元数据；不会绕过目标基线检查。
- 旧关联增加一致性校验：若 Action 记录的 Text 内容与已接受源动作提示明显不匹配，则自动重新识别；用户在面板中明确选择的 Text 仍作为手动覆盖保留。
- 真实 `Kitchen_Conservatory.blend` 只读回归：从已失效旧模型的三段 Action 向新骨架副本批量导入 1–150、150–224、224–293 帧，第一段 `-29` 帧过渡保留并生成 2 条 NLA；150 帧接缝最大误差 `1.4901161193847656e-08`，224 帧 `2.2351741790771484e-08`。另行单段导入第二段 150–224 帧成功。旧模型状态未变化，工程未保存，未调用 Hosted Generate。
- 自动导演 smoke、BA Workflow 全量 smoke、源码与 ZIP `extension validate` 均 PASS。发布包 `ba_animation_workflow-0.7.0.zip`：44,390 B，SHA-256 `9e78f6f6e3a7707ab41aa3902bf3ea532139178c549680cdfccc85ba99056a54`，包内只有 8 个运行文件。
- 正式安装与加强后的联合 profile smoke PASS：BA Workflow 0.7.0、PMB 0.9.1 等均 enabled/loaded，42 个必要操作器（含 3 个动作复用操作器）全部可用。安装版对真实工程再次通过单段与三段批量复用，结果与源码版一致；回滚备份为 `backups/profile-production-20260906-161712-499`。

## 2026-09-06：BA Animation Workflow 0.6.0 已有动作关联与无生成重新映射

- 每个新生成的目标 Action 现在会记录对应的 Blender Text 提示词、已接受的 Proscenium 源 Action、正式 Clip 帧段和关联格式版本；两类源数据均启用持久保留，保存工程后仍可重新映射。
- 高级设置新增“已有动作重新映射”：选择目标角色 Action 后自动恢复对应文本块和源动作；旧工程若没有关联元数据，会按正式帧段与源 Action 的提示词标签自动识别，文本也可在面板中手动改选。
- 替换只调用 Proscenium Motion Bridge 的本地重定向：新 Action 原位接管活动 Action 或原 NLA 条带，旧错误 Action 以 `_BAW_替换前` 后缀保留作为回退，不消耗动作生成额度。
- 对真实 `Kitchen_Conservatory.blend` 的第一、第二、第三段分别完成只读重新映射：三个旧式 Action 均正确关联“第一段 / 第二段 / 第三段”；第一段 `-29` 帧负滚动区完整保留；第二段 NLA 条带原位替换且第三段活动 Action 不受影响；第三段活动 Action 原位替换。工程未保存，未调用 Hosted Generate。
- 三段连续替换后，150 帧接缝最大可见矩阵误差为 `7.450580596923828e-09`，224 帧为 `1.4901161193847656e-08`；第 149、150、223、224 帧真实渲染未见新增位移或骨骼扭曲。
- 自动导演 smoke、BA Workflow 全量 smoke 与源码 `extension validate` 均 PASS。发布包 `ba_animation_workflow-0.6.0.zip`：41,330 B，SHA-256 `361e4777b59cfbebe7be5a0026e5cfa5e8d1a35f364e76af1d3759fe431ac556`，包内只有 8 个运行文件。
- ZIP `extension validate`、正式安装和联合 profile smoke 均 PASS：BA Workflow 0.6.0、PMB 0.9.1、MMD Tools 4.5.13 等均 enabled/loaded。安装版对真实工程再次完成三段无生成替换与四帧渲染，结果与源码版一致；回滚备份为 `backups/profile-production-20260906-154629-380`。

## 2026-09-06：BA Animation Workflow 0.5.12 Clip 接缝根位移修复

- 在用户更新后的 `Kitchen_Conservatory.blend` 中复现第 149→150、223→224 帧的小幅位置跳动。NLA 边界、骨架对象位置和身体短过渡均正常；偏移来自同时对 MMD `センター` 父骨和 `グルーブ` 子骨执行最终可见矩阵反解，使父级贡献被重复烘焙进 `グルーブ` 的局部 Location。
- 0.5.12 只对每条 Action-owned 根运动链的最高层骨骼执行可见姿态反解；子级根运动骨直接继承捕获的局部基矩阵，同时继续保留生成动作的整段相对位移/旋转。自动回归新增父级根骨 + 子级 Groove 通道，防止重复位移再次出现。
- 真实工程内存修复回归：150 帧 `センター / グルーブ / 下半身` 与上一段末帧的最大可见矩阵误差为 `1.4901161193847656e-08`；224 帧为 `7.450580596923828e-09`。第 149、150、151、223、224、225 帧渲染中接缝跳动消失。
- 从已接受的第三段源动作重新执行本地 PMB 重定向后，根运动链识别为锚点 `センター` + 子级 `グルーブ`；`max_root_child_start_error=1.1920928955078125e-07`、`max_root_delta_error=5.960464477539063e-08`、`max_unowned_basis_error=0.0`。工程未保存，未调用 Hosted Generate。
- 自动导演 smoke 与 BA Workflow 全量 smoke PASS；源码和 ZIP 均通过 Blender `extension validate`。发布包 `ba_animation_workflow-0.5.12.zip`：37,815 B，SHA-256 `81a00f69dab67811262c997e90daf0d6dbccce2a9ebc93634ac9eb1b3feb9bc6`，包内只有 8 个运行文件。
- 正式安装与联合 profile smoke PASS：BA Workflow 0.5.12、PMB 0.9.1、MMD Tools 4.5.13 等均 enabled/loaded。安装版对真实工程两处接缝的只读复测保持 150 帧最大误差 `1.4901161193847656e-08`、224 帧最大误差 `7.450580596923828e-09`，并完成第 149、150、151、223、224、225 帧渲染。回滚备份：`backups/profile-production-20260906-151511-799`。已删除确认有缺陷的 0.5.11 ZIP，避免误装；用户工程始终未保存，未调用 Hosted Generate。

## 2026-09-06：BA Animation Workflow 0.5.11 连续 Clip 身体扭曲修复

- 复核用户重新生成后的 `Kitchen_Conservatory.blend`，确认 Proscenium Motion Bridge 产生的原始第二段 Action 在第 150、151、180、224 帧均正常；严重扭曲由 BA 0.5.10 在生成后把每根身体骨的首帧姿态差贯穿到整段造成，而不是生成或重定向阶段造成。
- 0.5.11 将衔接拆成两类：带 Location 通道的根位移骨继续继承当前最终可见位置/朝向并完整保留原始相对运动；其余身体骨从上一段局部姿态平滑过渡到原始生成动作，过渡长度约为场景帧率的四分之一秒，结束后不再改写身体运动。未由新 Action 驱动的 D 骨、IK、裙发和附件仍保持零修改。
- 真实工程只读回归：根骨为 `センター`、`グルーブ`，身体骨 21 根，24 FPS 下过渡 6 帧；`max_root_delta_error=1.7881393432617188e-07`、`max_body_release_error=1.7881393432617188e-07`、`max_captured_body_error=2.980232238769531e-07`、`max_unowned_basis_error=0.0`。第 149、150、151、156、180、224 帧候选渲染未见 0.5.10 的整段肢体扭曲。工程未保存，未调用 Hosted Generate。
- 自动导演 smoke 与 BA Workflow 全量 smoke PASS；源码和 ZIP 均通过 Blender `extension validate`。发布包 `ba_animation_workflow-0.5.11.zip`：37,620 B，SHA-256 `15c577501ecca474a573525459602bf3fe4e0821c8dc0bd23dfdb97addc7ecbd`，包内只有 8 个运行文件。
- 正式安装与联合 profile smoke PASS：BA Workflow 0.5.11、PMB 0.9.1、MMD Tools 4.5.13 等均 enabled/loaded。安装版再次只读重建真实工程第二段并渲染第 149、150、151、156、180、224 帧，数值结果与源码版一致，未见整段身体/肢体扭曲。回滚备份：`backups/profile-production-20260906-132236-272`。已删除确认有缺陷的 0.5.10 ZIP，避免误装；用户工程始终未保存，未调用 Hosted Generate。

## 2026-09-06：BA Animation Workflow 0.5.10 MMD 辅助骨污染修复

- 撤回 0.5.9 的“整套骨架矩阵写入”实现。真实渲染证明它在衔接姿态求解时把捕获矩阵写入了新 Action 不拥有的 MMD D 骨、IK 与辅助骨；这些骨骼没有新关键帧恢复其 `matrix_basis`，因此第二段生成后连第一段也会出现手臂拉长等严重网格扭曲。
- 0.5.10 仍会采样并重定位新 Action 的完整逐帧局部运动，但临时姿态求解严格限制为该 Action 实际拥有的骨骼通道。未生成的 D 骨、IK、裙发、附件和其他辅助骨局部状态保持不变。
- 自动导演回归新增一个带可见约束但未被新 Action 驱动的 `ik_aux` 骨；衔接后其 `matrix_basis` 必须逐元素保持不变，同时原有位移、90° 朝向、135° 累计旋转、旧 NLA 边界及负滚动测试继续通过。
- 以只读方式打开用户工程 `Kitchen_Conservatory.blend`，在 180° 放置的 `伊落玛丽 _arm` 上验证：23 个 Action 骨骼完成重定位；其余 MMD 骨骼最大 `matrix_basis` 变化为 `0.0`；角色对象世界矩阵不变；第二段第 150→151 帧原始局部运动增量误差为 `2.086162567138672e-07`。
- 对同一工程实际渲染文件当前组合、仅第一段、仅第二段与候选修复四组状态；检查第 149、150、151、180、224 帧，候选修复不再出现 0.5.9 的手臂拉长或全片段扭曲，第二段中段和末帧与正常重定向结果一致。工程未保存，未调用 Hosted Generate。
- 自动导演 smoke、BA Workflow 全量 smoke、PMB 0.9.1 目标放置测试、源码与 ZIP `extension validate` 均 PASS；包内只有 8 个运行文件。发布包 `ba_animation_workflow-0.5.10.zip`：37,141 B，SHA-256 `3826675e95b5c97717b27dc9ac1803c1f587fca002c22c45587e992c0b67a10e`。已从 `dist` 移除确认有缺陷的 0.5.9 ZIP，避免误装。未调用 Hosted Generate。
- 正式安装与联合 profile smoke PASS：BA Workflow 0.5.10、PMB 0.9.1 和 BlendCap Bridge 0.4.0 均 enabled/loaded。安装版再次只读打开真实工程，数值回归保持 `max_unowned_basis_error=0.0`、`max_motion_delta_error=2.086162567138672e-07`；最终安装版实际渲染第 149、150、151、180、224 帧均无辅助骨拉伸或网格扭曲。回滚备份：`backups/profile-production-20260906-120804-924`。

## 2026-09-06：BA Animation Workflow 0.5.9 连续 Clip 位移与朝向继承

- 复核用户工程 `Kitchen_Conservatory.blend`：角色对象本身带约 180° 世界旋转，第二段输出仍记录了约 -180° 的 PMB 目标放置补偿，证明上游旋转目标修复没有丢失；异常发生在 BA 接收后的连续 Clip 整理阶段。
- 连续 Clip 不再只把当前可见姿态写到新 Action 首帧。插件会先隔离旧 NLA，采样新 Action 的逐帧局部运动增量，再把整段动作重定位到依赖图捕获的当前最终可见姿态。根位移会沿用当前位置，后续移动会跟随当前朝向，避免第二帧重新朝向源骨架正向。
- 上一段 `REPLACE` NLA 条带改为 `NOTHING` 外推：边界前仍完整求值原 Action 与负滚动区，边界后不再用旧片段独有通道污染新 Action，避免混合成扭曲姿态。每次连续生成还会自动迁移 0.5.8 及更早版本创建的 `BAW_上一段_` 条带，不触碰用户手工 NLA。
- 针对性回归覆盖已有位置、90° 当前根旋转、新片段 45° 相对旋转、位移方向继承，以及仅存在于旧片段的次级骨通道；首帧精确等于捕获姿态、片尾累计为 135°，旧次级骨通道在边界后不再泄漏。未调用 Hosted Generate。
- 安装后以只读后台方式打开用户真实工程 `Kitchen_Conservatory.blend`，直接在内存中对 `伊落玛丽 _arm` 的第一段 NLA 与第二段 Action 执行 0.5.9 整理：边界为 150，23 个新动作骨骼全部重定位；角色对象 180° 世界布置未改变，第二段原始第 150→151 帧局部运动增量保持误差为 `2.086162567138672e-07`，旧条带自动迁移为 `NOTHING`，第一段已写入通道在 149 帧保持不变。脚本明确未保存工程、未调用云端生成。
- 自动导演 smoke 与 BA Workflow 全量 smoke PASS，PMB 0.9.1 目标放置回归亦 PASS；源码和 ZIP 均通过 Blender `extension validate`，包内只有 8 个运行文件。未调用 Hosted Generate。发布包 `ba_animation_workflow-0.5.9.zip`：36,988 B，SHA-256 `43a9f6da5097a99c8d363e223db386d42849ef6ef10b962f764a95116a45d6a2`。
- 正式安装与联合 profile smoke PASS：BA Workflow 0.5.9、PMB 0.9.1 和 BlendCap Bridge 0.4.0 均 enabled/loaded；安装版自动导演回归再次通过位移/旋转整段重定位、旧 NLA 通道隔离及遗留条带迁移、负滚动保留与用户数据保护测试。回滚备份：`backups/profile-production-20260906-114240-627`。

## 2026-09-06：BA Animation Workflow 0.5.8 可见姿态衔接与负滚动保留

- 连续 Clip 不再只保存骨骼原始 `matrix_basis`；生成前会从 Blender 依赖图捕获约束、IK/FK 和 NLA 求值后的最终可见骨骼矩阵，并按父子层级将该姿态写入新 Action 首帧，仅写新 Action 已有通道。
- 新 Action 强制使用本段正式起点作为自定义 Action 起点并配合 `action_extrapolation=NOTHING`，因此不会在起点之前参与求值。
- 上一段 Action 转入 NLA 时会优先读取 Motion Bridge 保存的 `bam_preroll_frame_start`，扩展其自定义范围并从真实负滚动起点创建条带，避免只保留正式动作、裁掉预热边距。
- 针对性回归构造了局部位置 2、Copy Location 约束后可见位置 5 的角色：捕获与新首帧均为 5；上一段自定义正式范围从 100 开始但预滚动元数据为 40，新 NLA 条带从 40 开始，新 Action 从 100 才生效，50 帧仍正确求值旧过渡动作。
- 自动导演 smoke 与 BA Workflow 全量 smoke PASS，单 Clip、单一过渡边距、上一段 NLA、未生成次级骨通道、场景和用户数据保护均保持正常；未调用 Hosted Generate。发布包 `ba_animation_workflow-0.5.8.zip`：36,158 B，SHA-256 `d84c1bb23faba5c0d6783084627a8e5a18da9d7af2e230efa8114b66d77a8925`；源码与 ZIP 的 Blender `extension validate` 均通过。
- 正式安装与联合 profile smoke PASS：BA Workflow 0.5.8、PMB 0.9.1 和 BlendCap Bridge 0.4.0 均 enabled/loaded；安装版再次通过相同的约束后可见姿态、新 Action 起点限制、旧负滚动 NLA 保留和用户数据保护测试。回滚备份：`backups/profile-production-20260906-111215-486`。

## 2026-09-05：BA Animation Workflow 0.5.7 单一负滚动过渡边距

- 自动导演高级设置只保留“负滚动过渡边距”一个输入；删除 0.5.6 的“其中过渡帧”和稳定缓冲拆分显示。
- 负滚动区全部用于从初始姿态平滑进入正式动作首姿。例如当前帧 100、过渡边距 60，会向 Motion Bridge 传递 `settle_frames=0`、`transition_frames=60`，范围为 `40–99`，正式动作仍从 100 开始。
- 自动导演回归确认冗余 RNA/UI 字段不存在、方案不再记录独立 `buffer_frames`、无动作/时间轴起始与已有动作/NLA 连续衔接分支均保持正常。BA Workflow 全量 smoke PASS，未调用 Hosted Generate。
- 发布包 `ba_animation_workflow-0.5.7.zip`：35,620 B，SHA-256 `9537ef0b5ff534a7eb1b52a479c7836d30c8ceff59e0fcf2a8f905f635dba7a4`；源码与 ZIP 的 Blender `extension validate` 均通过。
- 正式安装与联合 profile smoke PASS：BA Workflow 0.5.7、PMB 0.9.1 和 BlendCap Bridge 0.4.0 均 enabled/loaded；安装版自动导演回归再次确认单一过渡边距、单 Prompt Block、NLA 连续性与用户数据保护正常。回滚备份：`backups/profile-production-20260905-174524-361`。

## 2026-09-05：BA Animation Workflow 0.5.6 负滚动缓冲与过渡

- 修复自动导演把全部负滚动边距写成静置帧、并强制过渡帧为 0 的问题。现在“负滚动总边距”由稳定缓冲与“其中过渡帧”组成；例如总计 60、过渡 20，会向 Motion Bridge 传递 `settle_frames=40`、`transition_frames=20`，正式动作起点不移动。
- 高级设置会实时显示实际拆分结果；若过渡帧大于总边距，会安全截到总边距，稳定缓冲变为 0，不会把预滚动范围拉长。
- 自动导演源码回归 PASS：无已有动作或位于时间轴起始时启用 40+20 预滚动，已有动作且不在起始时仍走当前姿态/NLA 连续衔接。Motion Bridge 骨骼级回归确认稳定段角度保持 0°、过渡段依次为约 23.33°/66.67°、正式首帧保持约 90°；未调用 Hosted Generate。
- BA Workflow 全量 smoke PASS，原有动作清理、相机灯光、保存重开、场景隔离及缓存所有权保护保持正常。发布包 `ba_animation_workflow-0.5.6.zip`：35,888 B，SHA-256 `1d768919dc8ac482420e26fa37a7ad02df351fb73a4883b9be9f7306454cf27d`；源码与 ZIP 的 Blender `extension validate` 均通过。
- 正式安装与联合 profile smoke PASS：BA Workflow 0.5.6、PMB 0.9.1 和 BlendCap Bridge 0.4.0 均 enabled/loaded；已安装目录的自动导演拆分回归与骨骼级缓冲/过渡插值回归再次 PASS，未调用云端生成。回滚备份：`backups/profile-production-20260905-173907-609`。

## 2026-09-05：BA Animation Workflow 0.5.5 单段总帧数

- 自动导演不再识别或拆分提示词内部的 Timeline、Pose Anchors、FPS、帧范围、总帧数和 Clip 标题；Blender Text 中的全部内容会原样成为唯一一个 Proscenium Prompt Block。
- 面板只保留一个“当前 Clip 总帧数”输入作为动作长度来源；动作从当前时间轴帧开始，帧率沿用当前场景。例如当前帧 100、总帧数 150，对应范围为 `100–249`。
- 删除旧时间解析器、自动 Pose Anchor 调度及 FPS/缺省秒数等旧设置残留；保留 0.5.3 多行文本编辑体验与 0.5.4 的连续 Action → NLA 非破坏衔接。
- Blender 5.1.2 源码回归 PASS：多行结构文本保持单段、面板总帧数与场景 FPS 生效、提示词内部时间指令不影响排程、旧 Action/NLA 连续性及用户场景数据保护保持正常；未调用 Hosted Generate。
- 发布包 `ba_animation_workflow-0.5.5.zip`：35,515 B，SHA-256 `fd7355023615d84bce371d0e68a201fe7a604b3cea0bc3fcd71a19ac44fd042e`；源码与 ZIP 的 Blender `extension validate` 均通过，包内只有 8 个运行文件。
- 正式安装与联合 profile smoke PASS：BA Workflow 0.5.5、PMB 0.9.1 和 BlendCap Bridge 0.4.0 均 enabled/loaded；39 个必要操作器、7 项 Scene RNA 与唯一 `BAW_PT_main` 均可用。已安装包的单 Prompt Block、总帧数、场景 FPS、连续 Clip/NLA、多行提示词与用户数据保护回归通过；未调用云端生成。回滚备份：`backups/profile-production-20260905-123242-552`。

## 2026-09-04：BA Animation Workflow 0.5.4 连续 Clip 动作保留

- 保留 0.5.3 的 Blender 原生多行提示词编辑器，并撤销未发布的剪贴板简化尝试。
- 当角色已有活动 Action 且当前帧不在时间轴起始时，生成前记录旧 Action；Motion Bridge 输出新 Action 后，将旧 Action 非破坏地放入 NLA，并在新 Clip 边界截断、保持末姿。新 Action 使用 `NOTHING` 外推，只从自身首帧开始接管。
- 回归验证旧 Action 关键帧数量与内容不变、旧段在新 Clip 之前正常求值、NLA 条带不重复、新 Action 在边界处恢复生成前当前姿态，未映射的裙发/附件通道仍不会被新增关键帧。
- 发布包 `ba_animation_workflow-0.5.4.zip`：40,146 B，SHA-256 `f2298929c812897499eb3e0e9a8a7f8bbef4b5a775d5f20d65d6179c25d38798`；源码与 ZIP 的 Blender `extension validate` 均通过，未调用 Hosted Generate。
- 正式安装与联合 profile smoke PASS：BA Workflow 0.5.4、PMB 0.9.1 和 BlendCap Bridge 0.4.0 均 enabled/loaded；39 个必要操作器、7 项 Scene RNA 与唯一 `BAW_PT_main` 均可用。已安装包的连续 Clip/NLA、多行提示词与用户数据保护回归通过。回滚备份：`backups/profile-production-20260904-171556-156`。

## 2026-09-03：BA Animation Workflow 0.5.3 多行 Clip 提示词

- “当前 Clip”由单行字符串输入升级为 Blender 原生 Text 数据块；面板可创建、选择、解除关联并在拆分区域中打开多行编辑器，换行、缩进和长文本随 `.blend` 保存。
- 首次新建会原样导入旧工程的短提示。只要已选择 Text，导演编译、场景刷新与完整生成都会优先读取 Text；导演 JSON 同时记录 `prompt_source`，便于审计输入来源。
- 离线回归覆盖 2 段 Timeline、Pose Anchor、90 帧范围、多行优先级、旧提示迁移、解除关联不删除用户文本、面板入口及既有单 Clip/衔接/场景保护测试，全部 PASS；未调用 Hosted Generate。
- 发布包 `ba_animation_workflow-0.5.3.zip`：39,649 B，SHA-256 `3cb7273c517a926417077a90e3b2eb9af2e26b832d2a373a25ad8fa9c76084a4`；源码与 ZIP 的 Blender `extension validate` 均通过，包内只有 8 个运行文件。
- 正式安装与联合 profile smoke PASS：BA Workflow 0.5.3、PMB 0.9.1 和 BlendCap Bridge 0.4.0 均 enabled/loaded；39 个必要操作器、7 项 Scene RNA 与唯一 `BAW_PT_main` 均可用。已安装包的多行提示词自动导演回归也通过，未调用云端生成。回滚备份：`backups/profile-production-20260904-161250-286`。

## 2026-09-03：BA Animation Workflow 0.5.2 / Proscenium Motion Bridge 0.9.1 同步

- 全自动与分步动作面板已接入 0.9.1 的“动作空间”“肢端防穿模”和修正幅度；导演 JSON 会保存这些设置，实际生成前再按方案应用。
- 连续 Clip 的当前姿态衔接只给输出 Action 已有的骨骼变换通道写首帧，不再给裙摆、头发、附件或物理骨等未生成通道新增曲线。
- 源码离线回归通过：单 Clip/FPS/帧范围解析、负帧预热、通道安全衔接、紧凑与高级 UI、场景幂等刷新和用户数据恢复全部 PASS；没有调用 Hosted Generate。
- 发布包 `ba_animation_workflow-0.5.2.zip`：38,489 B，SHA-256 `35ffab5c07008e882c1dd8ad00034330255c8ce7ec5623a291877fa05918da8d`；源码与 ZIP 的 Blender `extension validate` 均通过，包内只有 8 个运行文件。
- 配套 PMB 包：`proscenium_motion_bridge-0.9.1.zip`，41,239 B，SHA-256 `3a2cb625f549a0ee2e75ec71856916b4478eee264055c48ddd5ad312015c127e`。
- 正式安装与联合 profile smoke PASS：BA Workflow 0.5.2、PMB 0.9.1 和 BlendCap Bridge 0.4.0 均 enabled/loaded；36 个必要操作器、7 项 Scene RNA 与唯一 `BAW_PT_main` 均可用。已安装包的自动导演回归也通过，未调用云端生成。回滚备份：`backups/profile-production-20260903-200433-153`。

初始验收：2026-08-29；统一 UX 发布验收：2026-08-30；Bridge 维护：2026-08-31；自动导演实验版：2026-09-02

## 目标环境

- Blender 5.1.2，build hash `ec6e62d40fa9`
- Python 3.13.9（Blender 内置）
- Windows 11 Pro 25H2
- NVIDIA RTX 5080 16 GB

## 2026-09-03：BA Animation Workflow 0.5.1 单 Clip 与动作衔接修复

- 全自动入口改为一次只接收、生成一个 Clip；若输入含两个或更多 `## Clip`，在调用云端前明确停止。上一段验收后，用户移动时间轴并输入下一段，不再自动生成四段或创建批次 NLA。
- 单 Clip 中的 FPS、总帧数、Timeline、Pose Anchors 与 Root Motion 仍从提示词读取；片段局部帧号整体平移到当前帧。例如当前帧 100、提示词 1–225，实际正式动作范围为 100–324，动作块与锚点同步平移。
- 起始策略回归覆盖三种情况：无已有动作且当前帧 100、边距 60，正式动作从 100 开始、预滚动从 40 开始；已有动作且当前帧不在起点时，新输出 Action 的第 100 帧回写生成前角色姿态；已有动作但当前帧位于起点 1 时，预滚动从 -59 开始。取消或失败会恢复原 FPS、范围、Preview Range 与当前帧。
- 面板重排为“当前 Clip / 状态 / 动作设置 / 可选场景辅助”；自动搭建场景、自动布光、自动构图默认均为关闭，默认只生成角色动作。“负滚动帧边距”默认 60 帧。
- 方案 schema 升级为 3。源码、解包 ZIP 与正式安装目录的自动导演回归均 PASS；源码全量 smoke PASS，覆盖动作清理 `137 → 18` 点、镜头灯光、三帧渲染、保存重开、缓存 UUID 和场景隔离。
- 发布包 `ba_animation_workflow-0.5.1.zip`：37,748 B，SHA-256 `35a165f7bc6d7b3789c9f362a941930efc0b725ba03f8111aaf0bd925361e642`；源码与 ZIP 的 Blender `extension validate` 均通过，包内只有 8 个运行文件。
- 正式安装与联合 profile smoke PASS：BA Workflow 0.5.1 enabled/loaded，36 个必要操作器、7 项 Scene RNA 与唯一 `BAW_PT_main` 均可用。最终回滚备份：`backups/profile-production-20260903-163718-520`。
- 未调用 Animatica Hosted Generate，因此没有消耗额度；本次验证覆盖解析、排程、起始判断、首帧写入、UI、打包与正式安装，生成内容质量仍应在工程副本中逐 Clip 验收。

## 2026-09-03：BA Animation Workflow 0.5.0 提示词时间轴与多片段修复

- 对用户工程 `workflow.blend` 做只读检查：Scene 为 30 FPS、0–150 帧；SOMA 预览与角色输出 Action 都只到 150 帧，确认旧版始终采用面板默认 `5 秒 × 30 FPS`，未读取提示词时间参数。
- `creative_prompt` 上限从 2,048 提升到 65,535 字符；完整 `proscenium-prompt-writing` 文档不再被截断为第一段。
- 方案 schema 升级为 2，可解析中英文 FPS、总帧数/时长、Timeline、Pose Anchors、逐 Clip Root Motion 和自然简写；明确帧范围优先，重叠、越界与多 Clip FPS 冲突会报错而非静默回落。
- 多 Clip 以局部帧范围逐段调用 Proscenium，Pose Anchors 按帧串行生成；每段经 Motion Bridge 输出后放入目标角色的 `BAW Auto Director` NLA Track，并按全局帧位首尾相接。最终恢复全局 FPS 与帧范围。
- 真实“妈妈感”提示词回归结果：30 FPS、900 帧、30 秒、4 个批次、12 个 Prompt Blocks、11 个 Pose Anchors；全局范围为 `1–225 / 226–450 / 451–675 / 676–900`。提示词优先、面板回退、中文自然格式、重叠拒绝、长文本、NLA 双片段组装均通过自动测试。
- 源码全量 smoke PASS：动作清理 `137 → 18` 点、镜头灯光、三帧渲染、保存重开、缓存 UUID 和场景隔离保持正常；源码、解包 ZIP、正式安装目录的自动导演与真实提示词回归均 PASS。
- 发布包 `ba_animation_workflow-0.5.0.zip`：36,411 B，SHA-256 `d6d2ce74940cdc68e62bf0ce62c1bd91514665cfb7b145dc0d17f2c3d0181cd6`；Blender `extension validate` 通过，包内只有 8 个运行文件。
- 正式安装与联合 profile smoke PASS：BA Workflow 0.5.0 enabled/loaded，36 个必要操作器、7 项 Scene RNA 与唯一 `BAW_PT_main` 均可用。最终回滚备份：`backups/profile-production-20260903-120519-862`。
- 未调用 Animatica Hosted Generate，因此没有消耗额度；解析、调度、Pose 调用链、NLA 帧位和正式安装已验证，生成内容质量仍应由用户登录后用工程副本验收。

## 2026-09-02：BA Animation Workflow 0.4.1 单面板 UI 维护

- 将 `N → BA 动画` 中 9 个并列 `BAW_PT_*` 面板收敛为唯一 `BAW_PT_main`。正式 profile 枚举结果为 `workflow_panels=["BAW_PT_main"]`，不存在旧面板注册残留。
- 主面板顶部只保留“全自动 / 分步制作”模式切换。全自动默认布局只有一个主操作“生成动作并完成场景”；导演方案、单独场景生成、清理和详细参数统一进入“高级设置与辅助操作”。
- 分步模式通过一个阶段下拉选择工程准备、AI 动作、动作修正、镜头灯光、预览交付或传统 BVH；任一时刻只绘制当前阶段。项目阶段删除“创建目录 / 初始化场景”两个重复按钮，只保留“初始化工程目录与场景”。
- 安全清理、组件诊断和清理曲线参数默认折叠；交付阶段未展开安全清理时不会绘制任何删除操作。长状态与输出 Action 按实际侧栏宽度自动换行，避免横向拉宽 N 栏。
- 主按钮改为明确的“动词 + 结果”名称，并在按钮下加入可见的修改范围、保留项和下一步说明；操作器原有 tooltip 继续提供完整悬停描述。
- 源码与解包 ZIP 布局回归 PASS：默认自动模式恰好 1 个主运行键，高级区包含方案/场景辅助键，Run/Cancel/42% 进度状态可绘制；6 个分步阶段均可绘制且各自主要操作存在；长状态拆为多行；项目重复按钮与默认安全清理入口均不可见。
- 原自动导演数据安全 smoke 继续 PASS：教室/暖光识别、2 个 Prompt Blocks、10 个受控对象、重复重建无泄漏，清理恢复用户模型、World、Camera 与同名文本。原 BA Workflow 全量 smoke 继续 PASS：动作清理 137 → 18 点、四元数保留、镜头、灯光、三帧渲染、保存重开、缓存 UUID 与场景隔离均正常。
- 发布包 `ba_animation_workflow-0.4.1.zip`：30,613 B，SHA-256 `8f8da0734a3e4fba15c94c2afb60bdd514f47b9698d3cacfcb58172d5dfdda4d`；Blender `extension validate` 通过。
- 正式安装与联合 profile smoke PASS：BA Workflow 0.4.1 enabled/loaded，35 个必要操作器、7 项 Scene RNA 与 `BAW_PT_main` 均可用；安装目录自动导演/布局回归再次 PASS。最终回滚备份：`backups/profile-production-20260902-164944-895`。
- 尝试用 Windows Computer Use 做截图验收时，独立 Blender 5.1 启动器未暴露可控制窗口，主程序又被辅助层错误映射为 Steam Blender；按安全规则停止桌面输入。未以猜测坐标代替验收，结论基于正式安装目录的 Blender RNA、真实 `draw()` 布局探针与功能回归。

## 2026-09-02：BA Animation Workflow 0.4.0 实验性自动导演

- 新增独立 `auto_director.py` 与默认折叠的“实验性 · AI 自动导演”面板。输入用户角色骨架与创作描述后，生成带 schema/run ID 的透明 JSON 方案，并把动作拆为 1–4 个连续 Prompt Blocks。
- 本地方案编译器可判断摄影棚、教室、街道、舞台、户外五类 blocking 场景，以及中性、暖色、冷色、戏剧、日光五类灯光气氛；按角色世界包围盒生成场景、三点 Area Light、隔离 World 和全身/特写/动作镜头。
- 自动流程按 `方案 → 场景 → Connect → 官方 Skeleton → Generate → 异步轮询 → Preview → Accept/Bridge 输出` 运行。Generate 不使用同一 Python 调用内的阻塞等待；面板显示状态与进度，支持客户端取消。
- “生成后自动接受并输出”在 UI 中显式可见；关闭时流程停在 `PREVIEW_READY`，由用户检查后手动接受。开启并点击运行即表示同意自动 Accept。
- 所有生成对象、数据和文本均带 Scene UUID 与 `baw_owner/baw_role`。重建和清理只操作 `AUTO_DIRECTOR::` 数据；重复重建同时回收零引用 Mesh/Light/Camera，避免数据块泄漏。清理恢复原 Camera 与 World，不接管用户同名文本。
- 修复正式 profile 中新 World 可能没有默认节点的兼容边界：自动显式建立并连接 `Background → World Output`，确保环境色与强度生效。
- Blender 5.1.2 源码、解包 ZIP、正式安装目录三套自动导演 smoke 均 PASS：教室/暖光识别、2 个连续动作块、10 个受控对象、重复重建无对象或数据块泄漏、用户模型/World/Camera/同名文本完整恢复，面板 Run/Cancel/42% 进度状态均可绘制。
- 原 BA Workflow 全量 smoke PASS：137 → 18 个清理关键帧点、四元数保留、三帧 Eevee 渲染、保存重开、缓存 UUID/重解析点安全和场景副本隔离均保持正常。
- 发布包 `ba_animation_workflow-0.4.0.zip`：29,240 B，SHA-256 `dd965da63fcb77efe5db3c700a850972ff7474f2a5ee0f37db01a81068924843`；Blender `extension validate` 通过。
- 正式安装与联合 profile smoke PASS：BA Workflow 0.4.0、PMB 0.7.0、BlendCap Bridge 0.4.0 均 enabled/loaded，35 个必要操作器、7 项 Scene RNA 和 5 个关键面板全部可用。最终回滚备份：`backups/profile-production-20260902-135505-541`。
- 自动导演 smoke 明确记录 `cloud_generation_invoked=false`。本次未登录或调用 Hosted Generate，未消耗额度；因此已验证调度、界面、数据安全和组件注册，但自然语言动作质量仍需用户登录后用短动作单独验收。

## 2026-09-01：Proscenium Motion Bridge 0.7.0

- 输出动作新增分阶段进度：源 Action/NLA 准备、逐帧原生重定向、负帧缓冲写入、物理预热、
  恢复点保存；重新激活输出也显示 Action 绑定与逐帧物理预热。进度同时写入 Blender
  WindowManager 状态栏和单面板顶部，带等待光标与节流强制重绘。
- 进度属性使用 `SKIP_SAVE`；正常完成、无刚体世界、已烘焙缓存和异常回滚均在 `finally`
  清除进度与等待光标，避免工程保存后遗留“处理中”状态。
- 单面板按窄 N 栏重排：对象选择、根运动选项、映射按钮、目标切换和输出结果均纵向排列；
  长状态、警告、帮助文字和 Action 名按面板宽度自动换行。“激活”改为
  “重新激活并预热物理”，不再与长 Action 名挤在同一行。
- 所有可点击操作器补充详细 tooltip；关键按钮下加入短说明，明确会自动选择什么、恢复什么、
  保留什么，以及临时清理不会删除输出 Action。
- 维护审查修复多角色安全问题：重新激活优先使用输出 Action 的 `bam_target_object` 原目标，
  防止把上一角色 Action 误绑到当前新角色；原目标已删除时明确停止，旧版无元数据 Action 才
  回退到当前目标选择。
- 源码与解包 ZIP 的 factory-startup 回归均 PASS：完整/原地映射 `24/22`、原生 24 对输出、
  ToeBase 骨轴修正、起始缓冲、多角色切换、原目标重新激活、正常/故障进度清理均通过。
  280px 级布局探针确认长 Action 名拆为 3 行、五个主按钮文本完整、42% 进度条与阶段消息可见。
- 发布包 `proscenium_motion_bridge-0.7.0.zip`：35,338 B，SHA-256
  `aa9e260c0006b9c3177e0b975e7926c54bfe0502735e6b710bfb28639d5692ac`；通过 Blender 5.1.2
  `extension validate`。首次正式安装检查检测到用户 Blender 进程 PID 30200 正在响应，按安全策略
  未热覆盖；用户关闭 Blender 后安装成功。联合 profile smoke 确认 PMB 0.7.0 enabled/loaded、
  29 个必要操作器与面板无错误。直接从安装目录加载的完整映射/正常与故障进度清理、原目标
  重新激活和窄面板布局测试再次 PASS。最终回滚备份：
  `backups/profile-production-20260901-125735-822`。

## 2026-08-31：Proscenium Motion Bridge 0.6.0

- 移除运行时 BlendCap 依赖：SOMA 映射、rest-aware 世界空间旋转/位移求解、目标
  `matrix_basis` 回算和 Action 烘焙均由 `ba_motion_bridge/retarget.py` 实现；不再读取或改写
  `blendcap_retarget_pairs`，并移除“仅恢复映射”操作器和界面入口。
- `LeftToeBase / RightToeBase → つま先` 不再参与肢体绝对骨轴对齐，而是按源 Rest Pose
  到目标自身 Rest Pose 传递旋转增量，避免 SOMA 脚背向上的骨轴使 MMD 脚尖上翘。
- 单面板仍按五步顺序排列；第五步改名为“输出结果”，恢复按钮明确为
  “撤销本次应用（保留输出 Action）”。BA Animation Workflow 0.3.2 同步删除旧映射恢复状态读取，
  AI 核心组件不再要求 BlendCap。
- 无 BlendCap 的 factory-startup 回归 PASS：完整/原地映射 `24/22`，原生全链 bake 48 组通道键，
  T-Pose → A-Pose 上臂方向误差 `0°`；脚趾骨轴冲突回归首帧 `0°`，第二帧动作增量
  `19.999976°`；起始缓冲、负帧预览和两个多角色切换分支均 PASS。
- 两个 ZIP 解包后的发布代码再次在 factory-startup 下通过同一组映射、原生 bake、脚趾、
  起始缓冲和多角色切换回归；运行时确认 `blendcap_retarget_pairs` 不存在。
- BA Animation Workflow 0.3.2 源码 smoke PASS：137 → 18 个清理关键帧点、四元数保留、
  三帧渲染、保存重开、缓存所有权与场景隔离检查均通过。
- 发布包 `proscenium_motion_bridge-0.6.0.zip`：32,284 B，SHA-256
  `9a9d5994ced9df1d3d20b183f28d218014215b7945c75aaa3bbc7d60b2dfaed8`；
  `ba_animation_workflow-0.3.2.zip`：18,474 B，SHA-256
  `2f2cd7f58a4dff1f1c5db5b7b3bac9a981eb63109e8b4717b45ed58cead794a3`。
- 两个 ZIP 均通过 Blender 5.1.2 `extension validate`。首次安装尝试因检测到用户 Blender
  进程 PID 36840 而安全中止；用户关闭 Blender 后正式安装成功。联合 profile smoke PASS：
  PMB 0.6.0 与 BA Workflow 0.3.2 均 enabled/loaded，29 个必要操作器、Scene RNA 和面板无错误。
  安装目录清单确认为 0.6.0、包含 `retarget.py`，源码扫描无 BlendCap 引用；从安装目录在
  factory-startup 中直接加载的 24 对原生 bake 和 ToeBase 骨轴冲突测试再次 PASS，且 BlendCap
  未加载。最终回滚备份：
  `backups/profile-production-20260831-232738-415`。

## 2026-08-31：Proscenium Motion Bridge 0.5.0

- 根运动 UI 合并为一个策略选择器：自动跟随 Proscenium、强制完整位移、强制原地动作；
  体型比例与世界空间位移仅在最终模式为完整位移时显示。
- 目标角色切换不再只给阻断报错。仅在旧角色仍有恢复点且选中另一角色时，骨架区显示
  “恢复上一角色后切换”和“保留上一角色输出”两个上下文按钮；两个分支均通过回归。
- Blender 5.1 `Scene.frame_start` 的 RNA 硬下限确认为 0；负帧方案改为自动开启负值
  Preview Range，同时把当前帧和未烘焙 Rigid Body point cache 起点置于预滚动负帧。
  本机 MMD Tools 4.5.13 源码确认其更新与烘焙读取 point cache `frame_start`。
- 源码与解包发布包回归 PASS：MMD/ARP 映射 `24/22` 对、正式 Action 范围不变、
  负帧 Preview Range 与缓存起点同步、时间轴/缓存恢复、两个目标切换分支、注册顺序均通过。
- 发布包：`proscenium_motion_bridge-0.5.0.zip`，32,922 B，SHA-256
  `d000a5733e85a608e460675472f46e77b126bda3f9543b2d42c0b0ace7456cee`。
- 正式 Blender 5.1 profile 安装及联合 smoke PASS：7 个组件均 enabled/loaded，
  Proscenium Motion Bridge 版本为 0.5.0，30 个必要操作器、Scene RNA 与唯一 Bridge 面板正常；
  最终回滚备份：`backups/profile-production-20260831-222702-154`。

## 2026-08-31：Proscenium Motion Bridge 0.4.0

- 唯一面板的“输出设置”新增“初始姿态与起始缓冲”框；初始姿态可选当前角色姿态、
  目标 Rest Pose 或指定 Action 帧，静置帧与过渡帧均允许用户输入 0–1000。
- 正式动作原首帧不移动；预滚动关键帧写在首帧之前，静置段保持初姿，过渡段使用
  Smoothstep + quaternion SLERP。Action 自定义范围仍从真正首帧开始，NLA/导出逻辑上已剪边距。
- 只给映射主体骨写缓冲键，裙骨/发骨不写键；未烘焙 Rigid Body World 会扩展缓存起点并
  从预滚动起点逐帧求值。已烘焙缓存不会被擅自清除，而是给出明确警告。
- 恢复角色原状态会同时恢复物理缓存原起点；失败事务也会回滚缓存起点。
- 确定性缓冲测试 PASS：正式范围 `10–20`，预滚动起点 `5`，第 5 帧为 0° 初姿，
  第 10 帧仍为 90° 原首姿，次级裙骨无关键帧。
- 真实星野 MMD 源码与发布包隔离回归 PASS：正式范围 `1–20`，预滚动起点 `-29`，
  4,700 个关键帧点，世界旋转误差 `0°`；6 个约束、54 对旧映射、原 Action/NLA、
  物理缓存起点与故障事务全部恢复，临时 Action 残留 0。
- 发布包：`proscenium_motion_bridge-0.4.0.zip`，30,934 B，SHA-256
  `6b035f9377fa2a2aa7ce81913479bb0682b9a24d3cd4e68cc9f5c7dca64b0e82`。
- 用户明确授权后已升级正式 Blender 5.1 profile；联合 smoke 为 PASS：7 个组件均
  enabled/loaded，Proscenium Motion Bridge 版本为 0.4.0，旧 Bridge 模块未启用，
  30 个操作器、所需 Scene RNA 与唯一 Bridge 面板全部正常。回滚备份：
  `backups/profile-production-20260831-212323-476`。

## 2026-08-31：Proscenium Motion Bridge 0.3.1

- 插件从 BA Motion Bridge 更名为 **Proscenium Motion Bridge**；扩展 ID 与所有权标记改为
  `proscenium_motion_bridge`，旧 `ba_motion_bridge` 所有权值仍可安全清理，Scene RNA 与操作器
  前缀保留以兼容旧 `.blend` 工程。
- 只注册一个 `BAM_PT_proscenium_motion_bridge` 面板，依次排列“选择骨架 → 输出设置 →
  识别与检查 → 输出动作 → 结果与恢复”。
- 新增 Auto-Rig Pro profile，SOMA 肢体写入 `c_*_fk` 控制器而非内部 mechanism bones；
  输出时切到 FK，恢复时精确还原 IK/FK 自定义属性。
- 新增肢体静置方向补偿：在单次 BlendCap Classic 烘焙内去除 source/target rest swing，
  保留 bone-roll twist，不改变源骨架当前姿势。
- 截图对应场景隔离回归：左右上臂方向误差 `0° / 0°`，整臂误差
  `0.796967° / 2.515128°`，FK 输出和开关恢复均 PASS。
- 原生星野 MMD 隔离回归：24 对、1,880 个关键帧点、世界旋转误差 `0°`；6 个约束、
  54 对旧映射、原 Action/NLA 与故障事务全部恢复，临时 Action 残留 0。
- 映射/注册回归与 BA Animation Workflow 0.3.1 源码 smoke 均 PASS。
- 发布包：`proscenium_motion_bridge-0.3.1.zip`，27,597 B，SHA-256
  `81ca536bb76cc5424baa8a370f21963cd62b2aa6b099b76dab62b753091d6bae`；
  `ba_animation_workflow-0.3.1.zip`，18,495 B，SHA-256
  `89423cf6f780224392f3556319b7b85d71f6d264965c0abdb7ab49beb229595b`。
- 正式 Blender 5.1 profile 已完成备份、旧 Bridge ID 迁移、安装与联合 smoke；7 个组件均
  enabled/loaded，30 个操作器、所需 Scene RNA 与唯一 Bridge 面板全部 PASS。回滚备份：
  `backups/profile-production-20260831-194915-273`。
- 已安装 ZIP 中的 Bridge 代码再次通过截图场景回归；测试结束后两个工作区 `.blend` 隔离副本
  均已删除，用户原始文件未修改。

## 2026-08-31：BlendCap Motion Bridge 0.2.1

- BlendCap Motion Bridge 用户可见名称更改为 **BlendCap Motion Bridge**；为兼容升级，内部扩展 ID
  `blendcap_motion_bridge`、操作器和 Scene RNA 前缀不变。
- `BlendCap` N 标签下原有四个面板合并为唯一的 `BCMB_PT_main`，面板标题为
  `BlendCap Motion Bridge`；步骤顺序为“动作来源与角色 → 动作重定向 → MMD 表情 →
  VMD 与烘焙后处理”。
- 开发源码注册与 UI 顺序回归：`BLENDCAP_MOTION_BRIDGE_REGISTRATION_021=PASS`。
- 隔离安装包回归：`BLENDCAP_MOTION_BRIDGE_PACKAGE_021=PASS`；旧三个面板类型均不存在。
- 正式安装后 UI 类型/图标检查：`BLENDCAP_MOTION_BRIDGE_INSTALLED_UI_021=PASS`。
- 正式 profile smoke：7/7 组件加载，30 个必要操作器、5 个工作流关键面板通过；
  BlendCap Motion Bridge 版本为 0.2.1。
- 安装包：`dist/blendcap_motion_bridge-0.2.1.zip`，24,007 B，SHA-256
  `2d482cb4009cc8f78fa9b2f07c70ec42cb85ebf43cf1c8921f2d390d651c3805`。
- 升级前回滚备份：`backups/profile-production-20260831-191605-771`。

## 2026-08-30：统一 UX 发布包

目标组合：BA Animation Workflow 0.3.0、BA Motion Bridge 0.2.0、BlendCap Motion Bridge 0.2.0，配合 Proscenium Hosted 0.4.0、BlendCap 1.0.5、MMD Tools 4.5.13 与 Add Camera Rigs 1.8.2。

### 三个独立技术包

统一 UX 没有把插件源码合并。BA Animation Workflow、BA Motion Bridge 和 BlendCap Motion Bridge 仍拥有各自的 manifest、注册生命周期、版本号和发布 ZIP；可以分别安装、启用、升级与排错。Proscenium 仍是独立第三方插件，Bridge 只在其 `Proscenium` N 标签注入“MMD 输出”面板，并通过公开操作符衔接 Accept。

三个源码目录和最终 ZIP 均通过 Blender 5.1 `extension validate`：

| 包 | 大小 | SHA-256 |
|---|---:|---|
| `dist/ba_animation_workflow-0.3.0.zip` | 18,479 B | `d98dc12d9bf43b2268588a9aa7e153f7c7a34cb1e06a9b50944209970fb7b3f7` |
| `dist/ba_motion_bridge-0.2.0.zip` | 24,473 B | `b6b72edd51a6a092cc924c6d8b1ad329e8c07bf0eb09bc4dece9a0818b610d5a` |
| `dist/blendcap_motion_bridge-0.2.0.zip` | 23,494 B | `d9ab4a6952e4f8cf62295540f31e4fce5977ca0366dbba064de6fbf08b439482` |

### 统一界面实现检查

- BA Motion Bridge 0.2.0 注册 `BAM_PT_proscenium_output` 与默认折叠的 `BAM_PT_main`；前者直接位于 `N → Proscenium`。
- Proscenium 正在 Preview 时，主按钮显示“接受并输出到 MMD”，先执行 `proscenium.accept` 再检查并重定向；动作已接受时显示“一键输出到 MMD”。生成进行中时按钮锁定。
- BA Animation Workflow 0.3.0 将 `N → BA 动画` 分为工程与场景、AI 动作与 MMD 输出、动作清理与人工修正、镜头与灯光、预览/检查/安全清理五个阶段；传统 BlendCap → MMD 路径作为默认折叠的兼容区保留。
- BA 工作台只展示 Bridge 当前状态、上次输出、激活与恢复入口，不在 BA 标签复制 Proscenium 的 Generate/Preview 控件。
- BlendCap Motion Bridge 0.2.0 保持传统 BVH 语义，向 BA 兼容区提供“一键自动准备并安全重定向”；官方 SOMA 仍只走 BA Motion Bridge。

### 真实 MMD Bridge 回归

0.2.0 最终源码再次通过真实星野 fixture 回归：主链 24 对、20 帧 Accepted NLA 输出 1,880 个关键帧点、`Chest → 上半身2` 世界旋转增量误差 0°。腿链/腰取消约束快照、旧目标动画、BlendCap 映射与故障注入事务均完整恢复；没有临时 Action 残留。

该测试复用确定性官方 Canonical 动画，验证的是映射、Rest Pose、NLA 读取和数据安全；没有调用会消耗额度的真实 Hosted Generate。

### BlendCap Motion Bridge 0.2.0 隔离回归

Blender 5.1.2 使用 `--factory-startup` 从最终源码导入并运行全套回归，进程 exit 0、`failures={}`：

- `blendcap_motion_bridge.quick_retarget` 返回 `FINISHED`，受控 fake bake 恰好执行 1 次；FK-safe 路径通过，未相关约束保持不变；
- `prepare_in_memory` 生成 18 对当前映射，Blender CONFIG 写入次数为 0；
- `restore_previous_state` 恢复原 Action/Fake User、3 个约束基线、旧 1-row BlendCap pair table 及授权字段；新输出 Action 保留；
- SOMA 源拒绝、陈旧 pair table 拒绝、换成同骨名但不同目标对象后的授权/签名门禁均通过。

这证明传统 BVH 的“一键自动准备并安全重定向”及恢复闭环，不把 SOMA 语义或陈旧映射带入 Bridge 主线。

### 正式 Blender 5.1 profile 安装

关闭 Blender 后，正式安装脚本按 `BlendCap Motion Bridge → BA Motion Bridge → BA Animation Workflow` 顺序安装三个锁定 ZIP，并在同一正式 profile 运行 smoke，结果为 PASS：

- 已安装版本：BA Animation Workflow 0.3.0、BA Motion Bridge 0.2.0、BlendCap Motion Bridge 0.2.0；
- 7/7 个目标组件均 `enabled=true / loaded=true`；
- 30 个必要 operator、6 个 Scene RNA 与 5 个关键 Panel 全部存在；
- `errors=[]`，安装与 smoke 结束后 Blender 进程数为 0。

本次升级回滚点：

```text
D:\Agent Workspaces\BA_Animation_Workflow\backups\profile-production-20260830-201410-005
```

- 安装前 `userpref.blend` SHA-256：`1feb663db535a7c13bd5acc5affe76e8ec48af8f5460d119f2ba5a725f4601cf`
- 安装后 `userpref.blend` SHA-256：`620c7e2dbfb5a88b424a97d7a085e88f8d7d18e849627714dca707dd6540a0aa`

回滚目录包含安装前偏好与三个被替换扩展。恢复时必须先退出全部 Blender，不能在程序运行时覆盖偏好或扩展目录。

### 2026-08-31 GUI 验收与本轮清理

实际启动正式安装的 Blender 5.1.2 并逐页检查右侧 N 面板：

- `Proscenium` 标签同时显示 Hosted 原面板与 `MMD 输出 · BA Motion Bridge`；源/目标、动作状态、根运动模式、跟随原地模式、自动接受预览、一键输出及事务安全提示均正常显示；
- `BA 动画` 显示 `BA 动画工作台 0.3`，核心组件为 `4/4`，工程、AI 动作、清理/修正、镜头/灯光、交付检查五阶段可见；Bridge 高级恢复与传统 BVH 区默认折叠；
- `BlendCap` 标签显示 BlendCap Motion Bridge 0.2.0 的 `传统 BVH → MMD` 面板；自动识别、内存映射、一键安全重定向可见，preset、面部与 VMD 工具位于折叠高级区；
- 关闭验收窗口后，Blender GUI 窗口与进程均为 0。

精确清理本轮生成的三个隔离目录：

```text
smoke_runs/baw-0.3-source-smoke
smoke_runs/motion-bridge-real-fixture
smoke_runs/package-profile-0.3
```

同时删除三个源码树中的 `__pycache__`。保留最终 ZIP、源码、MMD2 0.2.0 回归测试、Canonical Skeleton 基准、旧版历史 smoke、预设恢复证据与正式 profile 回滚备份。

## 历史基线：BA Workflow 0.2.0 + Motion Bridge 0.1.0（2026-08-30）

### 构建与供应链

两份源码目录及两份最终 ZIP 均通过 Blender 5.1 `extension validate`，包内没有 `__pycache__`、测试或嵌套 ZIP。

| 包 | 大小 | SHA-256 |
|---|---:|---|
| `dist/ba_animation_workflow-0.2.0.zip` | 16,782 B | `125c167ec9e53306d56971f0274f263fd763d0443eb8dea78ac7e3081f8b37d6` |
| `dist/ba_motion_bridge-0.1.0.zip` | 19,347 B | `60dfc5f602a21f886c4ff0951c1f40447c128bd5d8da71bb54174f1ca7240ab6` |

静态编译：28 个 Python 文件通过。两个包在独立 `BLENDER_USER_CONFIG/SCRIPTS/EXTENSIONS/DATAFILES` 中安装成功；从最终包运行双注册顺序测试与 BA 全功能 smoke 均通过。

### SOMA → MMD 映射测试

合成骨架测试：

```json
{"status":"PASS","full_pairs":24,"in_place_pairs":22,"critical_gate":["右shin"],"registration_orders":2}
```

验证点：

- 只接受带 `proscenium_canonical_model=kimodo-soma-rp` 且满足官方 30 骨签名的源；
- 完整位移为 24 对，原地模式为 22 对；
- `LeftLeg → 足.L`、`LeftShin → ひざ.L`，不会复用旧 BVH 的错误腿语义；
- 缺右小腿等关键主链时 fail-closed；
- 重复 ROT 目标、重叠 LOC 轴和非等比对象缩放均拒绝；
- BA Workflow/Bridge 可按任意顺序注册，不需要硬 import 可选插件。

真实骨架使用 `动捕6.blend` 的工作区隔离副本；脚本要求 background、显式 `BAM_REAL_TEST_ALLOW=isolated-fixture-copy` 和专用 fixture 路径，且没有保存副本或原工程。

真实映射：星野（二年级）主链 `24/24`，关键缺失 0，可选缺失 0，没有选择 IK、捩、shadow 骨。

真实重定向：

```json
{
  "status": "PASS",
  "pairs": 24,
  "scale_ratio": 0.6829482316970825,
  "output_keys": 1880,
  "rotation_error_degrees": 0.0,
  "scoped_constraints": 6,
  "source_nla_restored": true,
  "original_target_state_restored": true,
  "failure_transaction_rolled_back": true,
  "previous_mapping_restored": 54,
  "temporary_actions": 0
}
```

输入先生成确定性官方骨架 Action，再按 Proscenium 0.4.0 Accept 逻辑放进 `Proscenium: Motion` NLA（Strip influence 1.0）并清空活动 Action。测试确认：

- Bridge 优先使用 BlendCap Classic 依赖图世界空间 bake；
- 输出是带 Fake User/owner 标签的独立 Blender 5.1 slotted Action；
- 原目标 Action 关键帧不变；Action、Action Slot、NLA 与 Fake User 状态可一键切回；
- 仅 6 个映射腿链 IK/明确腰取消约束被关闭并精确恢复，未相关约束逐项不变；
- `Chest → 上半身2` 世界旋转增量误差为 0°；
- 旧 54 对 BlendCap 内存表逐字段恢复；
- 在第一项约束被修改后故意抛错，源 Action/NLA/帧、目标 Action/Slot/NLA、约束、映射表与 Classic/Fast 全局开关全部自动回滚；
- 无临时 Action 残留。

### 被覆盖预设的恢复

旧版 BlendCap Motion Bridge 测试曾把以下星野预设从 54 对覆盖为错误的 17 对：

```text
C:\Users\Administrator\AppData\Roaming\Blender Foundation\Blender\5.1\config\blendcap\retarget_maps\blendcap_motion_bridge_星野_二年级_arm.json
```

恢复前文件已备份为 `backups/preset-recovery-20260830/overwritten-17pairs-before-recovery.json`，SHA-256 `AB73C6C52A25949E469D77AE1B6F0BE5E1CE58CBFFEACACD94C347F5CDE5341F`。

从未修改的原工程（SHA-256 `98D52536B87063128E7E75268D6BE940D86914505DAA4F6C119982EF5803C9FE`）内嵌 Scene Collection 提取 54 对，验证源/目标骨全部存在、无重复、隐藏 LOC 字段为默认值，规范化 pairset SHA-256 为：

```text
C509CDCF748221BED62B935D6EA78F36395A8F6AC57CE2EC95ED21C87B5085B3
```

恢复候选与正式配置文件均为 7,199 B，文件 SHA-256 `EE8F106B0689861A7C10AD6C586BB73AEFD976013BB408F297B0E055AA198246`。Blender 实际从 preset 下拉回载得到 54 对，缺失源/目标骨均为 0。Bridge 本身不再写 preset，避免再次互相覆盖。

### BA Workflow 回归与正式安装

源码与最终安装包各运行一次全功能 smoke：均为 PASS。合成 RAW 137 个曲线点，CLEAN 18 个；四元数/轴角保留、欧拉跨 ±179° 连续、用户同名数据和 World 保留、Scene copy 隔离、缓存 UUID 防护、三帧 Eevee 渲染与保存重开均通过。

正式配置安装前备份：

```text
backups/profile-motion-bridge-20260830-190247
```

- 安装前 `userpref.blend` SHA-256：`2e556e9a2c321b005571c87392496886671eee8d84e1dfa17f2f97b6e39f39ad`
- 安装后 `userpref.blend` SHA-256：`1FEB663DB535A7C13BD5ACC5AFFE76E8EC48AF8F5460D119F2BA5A725F4601CF`
- `startup.blend` SHA-256：`080F8809815BAD5717AC7761A7D959258F816DB75CE5889E0171F95CC37FD9C8`，未改变

正式 profile smoke：7 个组件均 `enabled=true / loaded=true`；版本锁为 BlendCap 1.0.5、BlendCap Motion Bridge 0.1.12、Proscenium 0.4.0、BA Workflow 0.2.0、Bridge 0.1.0；20 个必要 operator 与 6 个 Scene RNA 全部存在；`animaide_enabled=false`。

### 界面与清理

实际启动 Blender 5.1.2 后，`N → BA 动画` 显示统一 Proscenium → Bridge → 传统 BlendCap Motion Bridge → CLEAN/CORR → 镜头/灯光流程；六项依赖均显示“已启用”。Bridge 详细面板默认折叠，常用按钮不需要切换 N 标签。检查结束后 Blender 5.1/误启动的 5.2 窗口均已关闭。

测试完成后精确删除本轮 4 个隔离 smoke/fixture 目录及两个 `__pycache__`，共 65 个文件、16,071,792 B。保留源码、最终 ZIP、Canonical Skeleton 基准、恢复证据和 profile 回滚备份。

### 尚未宣称完成

- 未登录 Animatica，未执行会消耗额度的真实 Hosted Generate；
- 真实重定向测试使用确定性 synthetic canonical NLA，证明管线与事务安全，不代表自然语言生成质量；
- 仍需用固定 10–15 秒黄金动作测量脚滑、穿模、武器接触和人工修复时间。

## 历史基线：BA Workflow 0.1.1（2026-08-29）

### 扩展构建与清单验证

- `blender --command extension validate`：通过。
- `blender --command extension build`：通过。
- 构建包：`ba_animation_workflow-0.1.1.zip`
- SHA-256：`45d798628e0e9da4f6b1332beb0e4ccb8636c1cb1886424798f045976a240a3d`

### 隔离全功能测试

使用独立的 `BLENDER_USER_CONFIG/SCRIPTS/EXTENSIONS/DATAFILES`，未接触正式偏好。

已通过项目：

- 扩展注册、注销与重新安装。
- 项目目录创建、项目 UUID、缓存 sentinel 和 0.1.0 项目迁移。
- 盘符根、用户主目录、Blender 配置/安装目录均拒绝作为项目根。
- 现存 junction、dangling reparse point 和伪造缓存 marker 均不能触发写入或删除。
- 场景集合初始化可重复执行；复制 Scene 会重签 UUID 并创建独立集合。
- 同名用户集合、对象、相机、灯光和 World 均未被接管；保存重开后用户 World 仍存在且参数不变。
- 合成动捕 Action 从 137 个曲线点简化为 18 个。
- 原始 Action 保持 137 个曲线点且设置 Fake User。
- 欧拉角跨 ±179° 的清理结果保持连续；四元数/轴角曲线逐点保持不变。
- 清理 Action 进入 `BAW_MOCAP_BASE` NLA 层。
- 独立人工修正 Action 创建并保持底层动作求值。
- 自动 Key/Fill/Rim 三点灯。
- 中景目标相机和时间线切镜标记。
- 官方 Add Camera Rigs 的 Dolly Rig 调用。
- Blender 5.1 新 `media_type=VIDEO` 输出 API。
- 项目缓存安全清理只删除 UUID/sentinel 匹配的 `50_cache/baw_generated`。
- 0.1.0 Scene 只迁移严格集合结构；被旧版误标记的用户相机/灯光不会被认领或修改。
- Eevee 在第 1、31、61 帧成功渲染 320×180 PNG。
- 测试 `.blend` 与 JSON 报告成功保存。

结果文件：

- `smoke_runs/run-0.1.1-safety/90_exports/smoke_report.json`
- `smoke_runs/run-0.1.1-safety/90_exports/BAW_smoke_scene.blend`
- `smoke_runs/run-0.1.1-safety/60_renders_preview/smoke_0001.png`
- `smoke_runs/run-0.1.1-safety/60_renders_preview/smoke_0031.png`
- `smoke_runs/run-0.1.1-safety/60_renders_preview/smoke_0061.png`

附加安全测试：`BAW_SETUP_JUNCTION_GUARD=PASS`、`BAW_JUNCTION_GUARD=PASS`、`BAW_DANGLING_LINK_GUARD=PASS`、`BAW_LEGACY_SCENE_MIGRATION=PASS`。

### 正式配置联合加载测试

使用实际 Blender 5.1 偏好运行 `--background --disable-autoexec`，结果为 PASS：

| 模块 | enabled | loaded |
|---|---:|---:|
| `bl_ext.user_default.blendcap` | true | true |
| `bl_ext.user_default.blendcap_motion_bridge` | true | true |
| `bl_ext.blender_org.mmd_tools` | true | true |
| `bl_ext.user_default.ba_animation_workflow` | true | true |
| `bl_ext.blender_org.add_camera_rigs` | true | true |

`animaide_enabled=false`，未再出现残留启用状态。

版本断言：`BA Animation Workflow == (0, 1, 1)`。正式升级前偏好备份为 `backups/profile-20260829-185239`。

### 界面检查

实际启动 Blender 5.1.2 后，`BA 动画` N 面板可见，中文控件完整，状态正确显示：

- BlendCap：已启用
- MMD Tools：已启用
- Retarget：未检测（有意不装，避免与现有 BlendCap Motion Bridge 重复）
- Add Camera Rigs：已启用

工程、动作、镜头与灯光、预览与交付五组控件均在一个面板内可见，没有 UI 异常。

### 尚未宣称完成的测试

当前没有用户指定的单一“黄金角色 + 黄金动捕视频”，因此未对具体 BA 模型给出脚滑毫米数、穿模比例、面部 Morph 准确率或 10 秒端到端耗时结论。下一阶段应选一名常用角色和 10–15 秒固定素材做回归基准。

## Proscenium Hosted 0.4.0

安装日期：2026-08-29

供应链：

- 官方资产：`proscenium-blender-0.4.0.zip`
- 大小：650,630 字节
- SHA-256：`64a9d76c001be20e132ee236313ae244e98c38d2ef3b196c96d979ba4faf21b1`
- 哈希与 GitHub v0.4.0 Release API 的 `digest` 一致。
- ZIP 共 22 个条目，唯一顶层目录为 `proscenium_blender`；只有 Python 与一个 SOMA 参考 NPZ，没有 EXE/DLL/PYD、wheel、pip、CUDA/PyTorch、模型权重或安装脚本。

隔离配置测试：

- Blender 5.1.2 安装与启用：PASS
- `proscenium_blender == 0.4.0`：PASS
- Hosted 默认开启、Self-hosted 关闭：PASS
- 注册 → 注销 → 重新注册：PASS
- 保存测试 `.blend` 并重开：PASS
- Connect/Generate/Accept/Reject/Sign-in/Sign-out/Import Skeleton 操作符全部存在：PASS

正式配置测试：

- 安装位置：`C:\Users\Administrator\AppData\Roaming\Blender Foundation\Blender\5.1\scripts\addons\proscenium_blender`
- 正式安装目录 20 个发布文件逐个与官方 ZIP 计算 SHA-256：PASS，无缺失或漂移
- 与 BlendCap、MMD Tools、BlendCap Motion Bridge、BA Workflow、Add Camera Rigs 联合加载：PASS
- 无凭据 HTTPS 探针：`https://api.animatica.ai/mmcp` 返回 HTTP 200
- 公开模型：`kimodo-soma-rp`
- 导入 Hosted Canonical Skeleton：PASS，30 骨
- 场景设为 30fps、保存并重开：PASS
- 测试文件：`smoke_runs/proscenium-hosted-0.4.0/canonical_skeleton_smoke.blend`
- 隔离测试配置及重复插件副本已在验证完成后删除，共 1,842,136 字节；保留官方 ZIP、正式安装、回滚备份、测试脚本、指南和 Canonical Skeleton 测试工程

安装前回滚点：

`backups/profile-pre-proscenium-20260829-201436`

- 安装前 `userpref.blend`：`625aed146fb04e4f9a29a8b9c65a3dc0c60b283011c6c73f428fb917119eb965`
- 安装后 `userpref.blend`：`566d0c462b892712041089540ba697ce4db0cfd41183961a1fcdb8d43ab49a12`
- 安装前后 `startup.blend` 均为：`080f8809815bad5717ac7761a7d959258f816db75ce5889e0171f95cc37fd9c8`，确认未被修改

尚未完成：

- 当前没有 Animatica 账号凭据，插件状态为 `signed_in=false`；没有执行需要身份认证、会消耗额度的真实 Generate。
- v0.4.0 登录没有 OAuth/device code，必须由用户在 Blender 登录框输入邮箱和密码。凭据没有写入命令、测试脚本或日志。
- 尚未用具体 MMD 角色测量重定向质量、脚滑和人工修复时间。
