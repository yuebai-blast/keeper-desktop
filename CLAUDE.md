# CLAUDE.md

本文件为 Claude Code（claude.ai/code）在本仓库工作时提供指导。是项目纲领，动手前先读，并与 `docs/` 下的设计文档保持一致。

## 项目简介

**Keeper（留影）** 是一款本地优先的 AI 选片工具，定位为面向摄影师的付费桌面产品，工程上按产品级标准从零构建。

核心流程是两层级联漏斗（详见 [docs/product-flow.md](docs/product-flow.md)）：**分组 → 本地模型评分漏斗（层①）→ 在线 LLM 评分漏斗（层②）→ 用户 A/B 擂台终选**。

两条不可动摇的产品原则：

1. **照片不出本地**：原图只在用户机器上被读取；只有用于大模型打分的低清预览会临时上传，用完即焚。
2. **机器不替用户做最终淘汰**：机器的职责到「为每组递上一份足够好的候选」为止。最终留谁、是否整组舍弃，是用户在擂台上的权利。

## 架构总览（MVP：纯本地，无云端）

monorepo，两个组件各自启动：

| 组件 | 路径 | 技术栈 | 职责 |
| :-- | :-- | :-- | :-- |
| 桌面应用 | `apps/desktop/` | Tauri 2.x（Rust 壳）+ Vue3 + TS + Vite + Pinia | 文件 IO / 读 RAW / UI / A/B 擂台 / 本地存储 / 调度 sidecar |
| 推理服务 | `sidecar/` | Python 3.11 + FastAPI | 分组 + 本地评分（层①）+ 调大模型打分（层②） |

数据流、Scorer 可替换设计、未来云端中转的插入点，详见 [docs/architecture.md](docs/architecture.md)。

### 本地推理为什么是独立的 Python sidecar

分组（DINOv2）、人脸（InsightFace）、美学/质量（pyiqa）、传统 CV 这些本地推理的生态全在 Python。Tauri 通过 `externalBin`（sidecar）机制把打包后的 Python 服务随应用分发，前端经 localhost HTTP 调用它。

### Scorer 可替换：今天直调，明天接云

「给候选打分」抽象为 `Scorer` 接口，业务流程只依赖接口：

- `LocalDirectScorer`（本版）：sidecar 直连大模型 API（火山 Ark，OpenAI 兼容协议）。
- `CloudRelayScorer`（未来商业版）：改调自建云端中转层（鉴权 + 计量计费 + 加价）。

商业化时只需新增实现 + 切配置，**业务流程一行不改**。

## 常用命令

工具链版本与所有命令统一由 **mise** 管理（`mise.toml`），Python 依赖走 **uv**。一律用 `mise run <task>`。

```bash
mise install              # 装钉死版本的 python / uv / node / pnpm / rust
mise run install          # 同步 sidecar（uv sync）+ desktop（pnpm install）依赖
mise run sidecar          # 启动本地推理服务（FastAPI）
mise run sidecar -- --port 8761   # 透传参数给服务
mise run app              # 启动 Tauri 桌面应用（开发模式）
mise run test             # sidecar 测试
mise run test -- tests/test_ranking.py   # 单文件
mise run lint             # sidecar 代码风格检查（ruff）
```

## 关键约定

- **依赖来源**：sidecar 在 `sidecar/pyproject.toml` 声明、`uv.lock` 锁定；改完跑 `mise run install`。前端在 `apps/desktop/package.json`。
- **工具链钉死**：`[tools]` 里所有版本必须是具体版本号，禁止 `latest`，保证可复现。新增工具/命令一律沉淀到 `mise.toml`，不散落到零散脚本。
- **OpenCV 三包冲突**：`sidecar/pyproject.toml` 的 `[tool.uv] override-dependencies` 用「marker 永假」把 `opencv-python(-headless)` 从依赖树剔除，保住 `opencv-contrib-python` 的 `cv2.saliency`。别把它们加回依赖。
- **不静默降级**：本地推理依赖缺失或模型加载失败立刻抛异常，不悄悄退化。
- **API key 本地管理**：大模型 key 存在 `~/.config/keeper/`（0600 权限），可由 UI 录入或环境变量注入，绝不入库。
- **照片不出本地**：任何把原图发往网络的改动都违反核心原则；只有低清预览允许上传给打分服务。
- **中文书写**：CLAUDE.md、README、`docs/`、代码注释、Git 提交信息一律用简体中文；代码标识符/API 名保持英文。

## 尚未落地（按计划推进）

- `apps/desktop/` 的 Tauri 工程需用脚手架初始化（`pnpm create tauri-app`，模板选 Vue + TS），初始化后补全 `mise run install` 的前端依赖步骤。
- `sidecar/keeper_engine/` 目前是接口与骨架，按 docs/product-flow.md 的规则逐步实现。
