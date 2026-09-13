# 发布包

当前版本 **0.14.0**，优化操作逻辑、识别性能与工作台面板。对应 Git 标签 `v0.14.0`。

- 本地安装包：`ba_animation_workflow-0.14.0.zip`
- SHA256：`a9dbf47736087db123ec358e77eb61af51959e7c8d4c1aab7a9a3b5d2c2e4c19`
- 位置：`D:/Agent Workspaces/Agent Delivery/BA_Animation_Workflow/releases/0.14.0`
- [使用说明](docs/PARTS_GUIDE.md)、[优化与验证记录](docs/VALIDATION_0.14.0.md)

## 上一远端发布版

**0.12.0**，Git 标签 `v0.12.0`。

- Blender 扩展：`ba_animation_workflow-0.12.0.zip`
- SHA256：`acabb2c693ad2c62208878303351473283a3aab540265418982a054c012db867`
- 技能：`blender-animation-polish-1.1.0.zip`，SHA256 `ff544f7a2d3a534cad334ebd6233be5714952714e4bd2379d7d7bce1ad6c27e2`

插件ZIP只包含扩展代码；技能作为独立附件和源码 `skills/blender-animation-polish` 维护。本机插件安装包与逐文件清单位于 `D:/Agent Workspaces/Agent Delivery/BA_Animation_Workflow/releases/0.12.0`。技能包在 `Agent Delivery/Mama_Animation/Skills`。

`tools/build_latest.py` 可重建扩展ZIP，`--output-dir` 可覆盖输出位置。插件不包含角色、场景、第三方生成插件或账号设置。验证见 `docs/VALIDATION_0.12.0.md`，功能见 `docs/DELIVERY_GUIDE.md`。
