# macOS 数据布局与分级参考

分析 macOS 扫描结果时读这份。讲"东西存在哪、怎么辨认、归哪一级"。

## 关键目录

| 目录 | 装什么 | 典型分级 |
|---|---|---|
| `~/Library/Caches/*` | 应用/工具缓存（浏览器、Homebrew、pip、playwright） | 🟢 可自动清 |
| `~/.cache/*`、`~/.npm`、`~/.cargo`、`~/.gradle`、`~/.m2` | 缓存、工具环境、模型、凭据等可能混合 | 深查具体子项，禁止整根标绿 |
| `~/Library/Developer/Xcode/DerivedData`、`CoreSimulator` | 构建产物与模拟器设备数据 | DerivedData 通常可再生；模拟器含设备用户数据，走 Xcode 管理 |
| `~/Library/Containers/<UUID 或 bundleid>` | 沙盒应用数据（聊天记录、离线视频、设置） | 🟡 多为用户数据 |
| `~/Library/Application Support/*` | 应用数据（Chrome Profile、Claude VM、飞书） | 🟡 |
| `~/Downloads` 里的 .dmg/.pkg | 安装包残留 | 🟢 |
| `/Applications/*.app` | 应用本体 | 🔴 仅当重复/想卸时上灯，否则归蓝色 |
| 系统文件、APFS 本地快照 | 系统 | 不上灯，归蓝色"系统及其他" |

## 辨认"神秘 UUID 容器"

`~/Library/Containers/` 下 UUID 命名的大目录，要查清属于哪个 App：
- `ls` 进 `Data/Documents/`、`Data/Library/`，找带 bundle id 的子目录（如 `com.bilibili.bbad` → 哔哩哔哩）
- 大头常藏在隐藏目录（如 `.Downloads/` 里的 `.bilitask` 离线视频）
- 仍只读，别动文件

## 间接释放（写进 long_term，不上红灯）

- 系统"可清除空间"磁盘紧张时自动回收
- 重启释放部分 swap / 临时快照
- `brew cleanup --prune=all`、清 Xcode DerivedData
- 调整 Time Machine 本地快照保留策略

## 删除机制

`server.py` 在 macOS 用 osascript 调访达入废纸篓；首次弹自动化授权，点允许。
