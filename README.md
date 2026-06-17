# Keeper · 留影

> Keep the best, on your own machine. ／ 把最好的留下，留在你自己的电脑里。

**Keeper（留影）** 是一款面向摄影师与重度拍摄者的本地优先 AI 选片工具。它先把一次拍摄里相似的连拍自动归入「同一个瞬间」，再让每组依次穿过两层规则相同的级联漏斗：**层① 本地模型**按技术质量（锐度 / 曝光 / 人脸 / IQA 美学）打 0–100 分，**层② 在线大模型**按审美 / 表情 / 构图 / 语义打 0–100 分；每层都「≥60 分全进、不足保底数则按分补够」，并对每张给出可解释的去留理由；最后由你在 A/B 擂台上做最终裁决。

两条贯穿始终的原则：

- **照片留在本地** —— 原图永远不离开你的电脑；仅用于分析的低清预览会临时上云、用完即焚。
- **机器不替你做最终淘汰** —— 机器只负责递上一份足够好的候选（每层 ≥60 分的全进下一层，不足时按保底数补够，绝不替你砍掉够好的），最终留谁、是否整组舍弃，由你在擂台上说了算。

桌面端基于 Tauri，轻量、跨平台、数据尽在掌握。

---

## 下载与安装

到 [Releases](https://github.com/yuebai-blast/keeper/releases) 下载对应平台的安装包：

| 平台 | 产物 | 安装方式 |
| :-- | :-- | :-- |
| macOS · Apple 芯片（M 系列） | `.dmg`（文件名含 `aarch64`） | 打开 dmg，将 Keeper 拖入「应用程序」 |
| macOS · Intel 芯片 | `.dmg`（文件名含 `x64`/`x86_64`） | 同上 |
| Windows x64 | `.exe`（NSIS 安装器）或 `.msi` | 双击安装 |

> 产物文件名以 Releases 实际为准；按芯片选对应的 macOS 包。

**首次启动需联网**：应用会一次性下载约 1.6 GB 本地 AI 模型到 `~/.keeper/models`，之后完全离线运行——照片不出本地。首次下载期间启动画面会显示进度。

### 未签名产物的放行

本项目当前不做代码签名/公证，首次打开需手动放行：

- **macOS**：若提示「已损坏」或「无法验证开发者」，到「系统设置 → 隐私与安全性」点「仍要打开」；或在终端执行
  `xattr -dr com.apple.quarantine /Applications/Keeper.app`
- **Windows**：SmartScreen 拦截时点「更多信息 → 仍要运行」。

### 配置大模型

选片的层②评分需要火山方舟（Ark）API key：在应用「设置」页录入，或写入 `~/.keeper/ark_key`（权限 0600，Windows 依赖用户目录 ACL）。密钥绝不入库。

## 当前阶段：MVP（纯本地，无云端）

这一版**不含云端中转 / 计费 / 支付**。大模型由本地推理服务直接调用（API key 本地管理）。商业化的云端层是后续版本，架构上已通过 `Scorer` 接口预留了平滑替换的位置。

## 仓库结构

```
keeper/
├── CLAUDE.md              # 项目纲领：产品流程 + 架构 + 工具链约定（动手前先读）
├── docs/
│   ├── product-flow.md    # 选片两层级联漏斗 + 「≥60 全进、补足保底数」规则
│   └── architecture.md    # 三层架构 + Scorer 可替换设计 + 数据流
├── mise.toml              # 工具链钉死 + 命令（install / sidecar / app / test）
├── sidecar/               # Python 本地推理服务（FastAPI）
└── apps/desktop/          # Tauri 桌面应用（Vue3 + TS 前端 + Rust 壳）
```

## 快速开始

```bash
mise install          # 装钉死版本的 python / uv / node / pnpm / rust
mise run install      # 同步 sidecar 与 desktop 的依赖
mise run sidecar      # 启动本地推理服务
mise run app          # 启动桌面应用（另开一个终端）
```

> 工具链版本与所有命令统一由 **mise** 管理，详见 `mise.toml`。一律用 `mise run <task>`。
