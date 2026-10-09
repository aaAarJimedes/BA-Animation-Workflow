# 发布包

当前正式发行版 **0.14.0**，对应 Git 标签 `v0.14.0`。优化操作逻辑、识别性能与工作台面板。

- [正式发布楼](https://github.com/aaAarJimedes/BA-Animation-Workflow/releases/tag/v0.14.0)
- [Blender 扩展安装包](https://github.com/aaAarJimedes/BA-Animation-Workflow/releases/download/v0.14.0/ba_animation_workflow-0.14.0.zip)：`ba_animation_workflow-0.14.0.zip`
- SHA-256：`a9dbf47736087db123ec358e77eb61af51959e7c8d4c1aab7a9a3b5d2c2e4c19`
- 本机交付位置：`D:/Agent Workspaces/Agent Delivery/BA_Animation_Workflow/releases/0.14.0`
- [使用说明](docs/PARTS_GUIDE.md)、[优化与功能验证范围](docs/VALIDATION_0.14.0.md)

## 历史版本与技能

同一发布页保留 0.12.0、0.11.0、0.10.0 的原说明、安装包和构建清单；同名历史清单使用 `archive-版本-` 前缀。所有历史 Git 标签和提交指向保留。

- [历史资产名称、大小、SHA-256 与替代下载入口](https://github.com/aaAarJimedes/BA-Animation-Workflow/releases/download/v0.14.0/release-history-catalog-20261009.json)
- [全部发布资产 SHA-256 清单](https://github.com/aaAarJimedes/BA-Animation-Workflow/releases/download/v0.14.0/SHA256SUMS-20261009.txt)
- [独立技能 blender-animation-polish 1.1.0](https://github.com/aaAarJimedes/BA-Animation-Workflow/releases/download/v0.14.0/blender-animation-polish-1.1.0.zip)，SHA-256 `ff544f7a2d3a534cad334ebd6233be5714952714e4bd2379d7d7bce1ad6c27e2`

插件 ZIP 只包含扩展代码；技能作为独立附件及源码 `skills/blender-animation-polish` 维护，不包含角色、场景、第三方生成插件或账号设置。0.13.0 为本地开发阶段，不虚构其发行包。

`tools/build_latest.py` 可重建扩展 ZIP，`--output-dir` 可覆盖输出位置。本机本次重建 0.14.0 与原功能验收包的 SHA-256 完全一致，包内文件与已有版本标签一致；发行楼 13 个真实资产均已重新下载验证。这不扩大原功能验收范围。

发布规则见 [GitHub 交付维护](docs/GITHUB_DELIVERY.md)。恢复资料保存在所属任务的 `Agent Temp/BA_Animation_Workflow/github-maintenance/2026-10-09` 下。
