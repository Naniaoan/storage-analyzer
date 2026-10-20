# Storage Analyzer · 持续优化版

> 基于 **数字生命卡兹克（Khazix）** 的 `storage-analyzer` Skill 继续优化，由 [Naniaoan](https://github.com/Naniaoan) 维护。原作和本版本的改动均按 MIT 许可证分发，保留原作者版权声明。这是独立维护的衍生版本，并非原作者官方发布。

[上游项目](https://github.com/KKKKhazix/khazix-skills) · [原始 Skill](https://github.com/KKKKhazix/khazix-skills/tree/main/storage-analyzer) · [来源与改动](UPSTREAM.md)

面向 macOS / Windows 的磁盘分析 Skill：找占用大户、深入大目录、识别疑似卸载残留，并把报告整理为用户可判断的具体文件和子功能。

## 优化了什么

- **从大目录深入具体对象**：识别大文件、工具版本、模型、附件、数据库、虚拟机和临时资源包，而不是只列目录排行榜。
- **按对象给建议**：默认展示具体内容、大小、建议、清理代价与下一步；父目录和完整核验折叠为背景。
- **浏览器缓存按站点识别**：从 CacheStorage 索引提取站点线索，让用户按站点判断离线资源是否需要保留。
- **卸载残留与时间证据**：分别核对应用元信息、安装副本、进程、共享组件与内部修改时间，区分已确认事实和待核项。
- **保留决定和快照校验**：用户明确保留的对象、依赖未核清对象和来源不匹配/过期的报告禁用相应清理入口；避免父子重复计数。

分析默认只读。**目录占用不等于可释放空间，文件旧不等于没用，缓存目录也可能包含运行环境。** 清理须在用户明确授权范围内执行；移到废纸篓后，清空才释放空间。

## 安装

需要 Python 3；扫描脚本只使用标准库。将本仓库放进支持 Skill 的工具对应技能目录，例如 Codex：

```bash
git clone https://github.com/Naniaoan/storage-analyzer.git ~/.codex/skills/storage-analyzer
```

如果目标目录已存在，先保留现有版本和本地改动，再选择替换或合并；不要直接覆盖。其他支持 `SKILL.md` 的工具按其技能目录安装。

安装后向 Agent 提出：“扫描磁盘，找出值得清理的具体大文件和子目录，并生成报告。”完整行为规则见 [SKILL.md](SKILL.md)。

## 脚本入口

```bash
python3 scripts/scan.py > /tmp/storage_scan.json
python3 scripts/deep_scan.py /absolute/path > /tmp/storage_details.json
# macOS 可选：本地应用归属证据
python3 scripts/app_evidence_macos.py --scan-json /tmp/storage_scan.json > /tmp/storage_apps.json
```

Agent 读取概览、深查和依赖证据后，编写 analysis JSON（结构见 `scripts/build_report.py` 和 `references/decision-presentation.md`），再生成报告：

```bash
python3 scripts/build_report.py /tmp/storage_analysis.json /tmp/storage-report.html
# 可选本机操作服务；用户点击并确认才执行白名单内动作
python3 scripts/server.py /tmp/storage_analysis.json
```

`scan.py` 不会独立完成全部语义分析，服务也不是实时扫描器。重新扫描需重新采集证据、生成分析与报告。Windows 代码路径保留，但本衍生版本尚未经真实 Windows 环境端到端验证。

## 后续迭代

本仓库作为持续维护入口，后续优化继续提交到这里。直接在仓库改动后，检查并提交：

```bash
python3 -m unittest discover -s tests -v
git diff
git add SKILL.md scripts references assets tests tools README.md UPSTREAM.md LICENSE .gitignore
git commit -m "Describe the improvement"
git push
```

如果改动先发生在本机已安装的 Skill，可先预览差异，再同步到此仓库：

```bash
python3 tools/sync_from_installed.py
python3 tools/sync_from_installed.py --apply
```

同步只复制 Skill 源文件，不读取或上传扫描报告；不自动提交或推送。仍须检查 `git diff`。新增文件会被复制；源端删文件时仅提示，需人工核对后删除仓库旧文件。

**不要提交真实扫描报告、应用数据、聊天内容、账户标识或带个人路径的截图。** 仓库不含本机扫描结果。

## 验证与授权

本版本在 macOS 上做过只读扫描、报告交互及临时夹具验证；没有靠删除用户文件来测试。仓库回归测试可独立运行：

```bash
python3 -m unittest discover -s tests -v
```

MIT 许可证见 [LICENSE](LICENSE)。感谢数字生命卡兹克提供原始 Skill。
