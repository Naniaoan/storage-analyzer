# 上游来源与衍生说明

- 原作者：数字生命卡兹克（Khazix）。
- 上游仓库：https://github.com/KKKKhazix/khazix-skills
- 原始目录：`storage-analyzer/`。
- 发布整理时核对的上游目录最近提交：`b429d4c769a5446971edc5b825aaf097fa143bb3`。此信息用于溯源，不表示当前代码基于该提交逐文件重放，或持续与上游完全同步。
- 衍生维护者：[Naniaoan](https://github.com/Naniaoan)。
- 本仓库首次公开整理：2026-10-20。
- 上游许可证：MIT。LICENSE 保留原作者版权声明；本仓库改动也使用 MIT。

本版本在原始存储分析 Skill 基础上继续迭代，重点加入：分层深查、具体对象建议、卸载残留核验、内部文件修改时间、用户保留/共享依赖限制、扫描来源校验与渐进披露报告。

新增/改进的实现主要位于 `scripts/deep_scan.py`、`scripts/app_evidence_macos.py`、`scripts/build_report.py`、报告模板及 `references/`；扫描和本机服务也随经验作了调整。本仓库不代表上游作者对这些改动提供背书或维护承诺。

后续改动由 Git 提交历史记录；吸收上游变化时继续保留其来源与版权信息。
