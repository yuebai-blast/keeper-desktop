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
mise run localscore -- /path/to/img.jpg   # 对单张图跑层①评分并打印明细（调试/标定）
```

## sidecar HTTP 契约（desktop ↔ sidecar 唯一接口）

服务只绑 `127.0.0.1`，默认端口 **8761**（`mise run sidecar -- --port` 改），前端经 `VITE_SIDECAR_URL` 覆盖基址。CORS 仅放行 localhost / `tauri://localhost`。端点定义在 `sidecar/keeper_engine/server.py`，前端客户端镜像在 `apps/desktop/src/api.ts`——**改任一端的请求/响应结构，两边都要同步**。

| 端点 | 作用 | 就绪门禁 |
| :-- | :-- | :-- |
| `GET /health` | 存活 + 层①模型就绪态（`loading`/`ready`/`error`），后台预热线程更新 | — |
| `GET /thumbnail?path=&size=` | sidecar 解码（含 RAW/HEIC）并缩放出 JPEG，带磁盘缓存；只走 localhost | — |
| `POST /group` | 把照片路径聚成「瞬间组」 | 需 `ready`，否则 503 |
| `POST /assess` | 层①本地评分 + 漏斗收口出 survivors | 需 `ready`，否则 503 |
| `POST /score` | 层②大模型打分 + 组装 PK 候选集 | 不依赖本地模型，缺 key/网络 → 502 |

容错约定：批量端点对**单张读图失败记入 `errors` 不中断**；本地模型整体不可用（预热失败/缺依赖）才 503，大模型不可用才 502——一律显式报错，不静默降级。

## 漏斗管线模块地图（最关键逻辑）

数据流：`grouping`（第0步分组）→ `prescreen`（层①逐张打分）→ `scorer`+`ranking`（层②大模型打分+组PK）。两层共用同一筛选规则：

- `grouping.py` — 把相似连拍聚成「瞬间组」。综合相似度 = 语义余弦(DINOv2) × 时间衰减(EXIF) × 人脸因子(主脸 ArcFace)。人脸因子专门把「同场景、同时间但不同人」拆成不同组；任一张无脸则因子=1，退回纯语义+时间。阈值在文件顶部，**在真实人脸上标定**。

- `funnel.py` — **全系统最关键**。`apply_funnel(scored, n)` 是两层通用的筛选规则（≥60 全过、不足保底数按分补、输入不足全放行）。改它影响整个产品行为。
- `params.py` — 保底数：`N = max(ceil(总数×20%), 3)`（层②），`M = ceil(1.5×N)`（层①）。
- `prescreen.py` — 层①合成分（TOPIQ + CLIP-IQA+ + 主体锐度，再按闭眼/脱焦/曝光等扣分）；阈值是集中在文件顶部的可调旋钮，**在真实照片上标定**。
- `vision.py` — 本地模型懒加载单例（DINOv2 / InsightFace / pyiqa）。模型缓存固定到 `~/.cache/keeper/models`。层①只用 InsightFace 检测+关键点（不载识别模型，层①用不到）；分组另起一个「检测+识别」实例取人脸身份 embedding。⚠️ 识别模型（ArcFace，`buffalo_l`）仅限非商用研究，**付费产品商用前需替换或单独授权**——这点对整个 `buffalo_l` 包（含层①在用的检测/关键点）都适用。
- `scorer.py` — `Scorer` 协议（唯一会演化为云端中转的环节）；`LocalDirectScorer` 直连火山 Ark，提示词在 `prompts/layer2_score.md`（不改代码即可迭代）。

桌面端：文件系统访问（导入扫图、归档写回）**只在 Rust 壳**（`src-tauri/src/lib.rs` 的 `import_photos` / `archive_decisions` 命令），前端碰不到 FS；前端状态在 Pinia stores（`engine` 连接态、`library` 库/分组/评分/裁决/归档）。

## 环境变量速查

| 变量 | 作用 |
| :-- | :-- |
| `VITE_SIDECAR_URL` | 前端覆盖 sidecar 基址（默认 `http://127.0.0.1:8761`） |
| `KEEPER_DEVICE` | `cpu`（默认最稳）/ `cuda`；pyiqa 在 MPS 易炸，固定不走 MPS |
| `KEEPER_MODELS_DIR` | 本地模型缓存根（默认 `~/.cache/keeper/models`） |
| `KEEPER_DINO_MODEL` / `KEEPER_FACE_PACK` | 切分组/人脸模型（默认 `facebook/dinov2-small` / `buffalo_l`） |
| `ARK_API_KEY` | 大模型 key；也可写入 `~/.config/keeper/ark_key`（0600），绝不入库 |
| `KEEPER_ARK_MODEL` / `KEEPER_ARK_BASE_URL` / `KEEPER_ARK_CONCURRENCY` | Ark 模型 id / 基址 / 并发数 |

## 关键约定

- **依赖来源**：sidecar 在 `sidecar/pyproject.toml` 声明、`uv.lock` 锁定；改完跑 `mise run install`。前端在 `apps/desktop/package.json`。
- **工具链钉死**：`[tools]` 里所有版本必须是具体版本号，禁止 `latest`，保证可复现。新增工具/命令一律沉淀到 `mise.toml`，不散落到零散脚本。
- **OpenCV 三包冲突**：`sidecar/pyproject.toml` 的 `[tool.uv] override-dependencies` 用「marker 永假」把 `opencv-python(-headless)` 从依赖树剔除，保住 `opencv-contrib-python` 的 `cv2.saliency`。别把它们加回依赖。
- **不静默降级**：本地推理依赖缺失或模型加载失败立刻抛异常，不悄悄退化。
- **API key 本地管理**：大模型 key 存在 `~/.config/keeper/`（0600 权限），可由 UI 录入或环境变量注入，绝不入库。
- **照片不出本地**：任何把原图发往网络的改动都违反核心原则；只有低清预览允许上传给打分服务。
- **中文书写**：CLAUDE.md、README、`docs/`、代码注释、Git 提交信息一律用简体中文；代码标识符/API 名保持英文。

## 进度与尚未落地（按计划推进）

已落地：分组、层①评分、层②大模型打分、PK 候选组装、缩略图缓存、桌面端 A/B 擂台终选（`src/components/Arena.vue`）与归档写回（复制/移动/仅清单）。

分组已接入人脸身份（主脸 ArcFace）拆开「同场景不同人」。

尚未落地：
- 人脸**集合**相似度：当前只取「主脸」，多人合影（一张 A+B、另一张 A+C）区分不准，需升级为多脸集合匹配。
- 服务端编排端点（如 `/assemble`，见 `server.py` 末尾 TODO；`assemble_pk_set` 已可复用）。
- `CloudRelayScorer`（商业版云端中转，按 `Scorer` 协议新增实现 + 切配置即可，业务流程不改）。
- 各阈值/权重旋钮仍需在真实照片集上标定。
- **商用授权**：`buffalo_l`（含分组用的 ArcFace 识别 + 层①的检测/关键点）仅限非商用研究，商用前必须替换或授权。
