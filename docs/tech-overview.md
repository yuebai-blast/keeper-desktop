# 技术总览

本文从**工程实现**角度讲清 Keeper 各部分用了什么技术、逻辑怎么落地，面向要动手改代码的开发者。

它与另两篇文档分工：

- [architecture.md](architecture.md)：高层架构、组件边界、数据流（什么离开本地）、Scorer 演进方向。
- [product-flow.md](product-flow.md)：产品规则——两层级联漏斗、保底数 N/M、A/B 擂台。**漏斗规则以它为准**。
- 本文：技术栈 + 实现细节（分层、DI、就绪态、模型、分组/评分算法、API 契约、前端结构）。

---

## 1. 仓库与工具链

monorepo，两个各自启动的组件：

| 组件 | 路径 | 技术栈 |
| :-- | :-- | :-- |
| 桌面应用 | `apps/desktop/` | Tauri 2.x（Rust 壳）+ Vue 3 + TypeScript + Vite + Pinia |
| 推理服务 | `sidecar/` | Python 3.11 + FastAPI；本地模型 + 大模型打分 |

工具链版本与命令统一由 **mise**（`mise.toml`）管理，版本全部钉死（禁 `latest`）；Python 依赖走 **uv**（`pyproject.toml` + `uv.lock`），前端走 **pnpm**。

```bash
mise install              # 装钉死版本的 python / uv / node / pnpm / rust
mise run install          # 同步 sidecar(uv sync) + desktop(pnpm install) 依赖
mise run sidecar          # 启动推理服务（FastAPI，默认 127.0.0.1:8761）
mise run app              # 启动 Tauri 桌面应用（开发模式）
mise run test / lint      # sidecar 测试 / ruff
mise run localscore -- <img>   # 对单图跑层①评分并打印明细（标定用）
```

> **OpenCV 三包冲突**：`pyproject.toml` 的 `[tool.uv] override-dependencies` 用「marker 永假」把 `opencv-python(-headless)` 从依赖树剔除，保住 `opencv-contrib-python` 的 `cv2.saliency`。别把它们加回去。

---

## 2. 后端 sidecar

### 2.1 技术栈

| 用途 | 技术 |
| :-- | :-- |
| HTTP 服务 | FastAPI + uvicorn，仅绑 `127.0.0.1` |
| 数据模型/校验 | pydantic v2 |
| 配置 | `pydantic-settings`（`~/.keeper/config.toml` + `KEEPER_*` 环境变量） |
| 状态持久化 | `SQLModel`（sqlite，模型下载/加载状态） |
| 依赖注入 | `dependency-injector`（声明式容器） |
| 语义特征（分组） | DINOv2（`facebook/dinov2-small`，via transformers + torch） |
| 人脸检测/关键点/识别 | InsightFace（`buffalo_l`，via onnxruntime） |
| 画质/美学评分 | pyiqa：TOPIQ-nr / TOPIQ-nr-face / CLIP-IQA+（torch + timm） |
| 传统 CV 信号 | opencv-contrib（saliency）、numpy、scipy（层次聚类） |
| 影像 IO | Pillow + pillow-heif（HEIC）+ rawpy（RAW 内嵌预览）+ piexif |
| 大模型打分 | openai SDK（火山 Ark，OpenAI 兼容协议） |

### 2.2 分层架构（Spring Boot 式 + DI）

`sidecar/keeper_engine/` 按职责分层，依赖方向：**controller → service → client**，配置与值对象横切。

```
main.py            启动入口（argparse + uvicorn）
app.py             FastAPI 工厂：建容器 → wire → CORS → lifespan 预热 → 注册路由
container.py       DI 容器：一处装配全部 provider

controller/        路由层，只接线（@inject 注入 service）：health / thumbnail / group / assess / score
service/           领域服务与编排（OOP 类）
  grouping_service     分组：embed_photo（用 vision）+ cluster（静态纯算法）+ group 编排
  prescreen_service    层①单张评分（用 vision 的 IQA/人脸信号）
  funnel_service       两层通用漏斗 apply_funnel（静态）
  params_service       保底数 N/M（静态）
  ranking_service      层②出口：漏斗 + PK 组装
  assess_service       /assess 编排（就绪门禁 + 逐张容错 + 漏斗收口）
  scoring_service      /score 编排（预览 → Scorer → 漏斗 → PK）
  readiness_service    模型预热与就绪态（见 2.4）
client/            外部依赖（DI Singleton）
  vision_client        本地模型懒加载（DINOv2 / InsightFace / pyiqa）
  scorer               Scorer 协议 + LocalDirectScorer（直连 Ark）；提示词在 client/prompts/
config/settings.py 集中配置（pydantic-settings）：~/.keeper/config.toml + KEEPER_* 环境变量加载
request/ response/ vo/   入参 / 出参 / 领域值对象
enumeration/ exception/ converter/   枚举 / 领域异常 / 漏斗结果→带 origin 条目
util/              纯函数工具（imaging 影像IO、signals CV信号）——非 Java 语言工具不强制成类
```

设计取舍：

- **有依赖/有状态的是注入式类**（service 编排、client）；**纯算法是静态方法**（`cluster`、`apply_funnel`、`compute_n/m`），算法标定阈值随各模块就近保留、**不进 config**，便于单测与调参。
- 无数据库，故**不设** `mapper` / `entity`。
- 传输对象由 `request`/`response` 覆盖，领域值对象在 `vo`，不另设 `dto`。

### 2.3 DI 容器（`container.py`）

`dependency_injector` 声明式容器一处装配；controller 包通过 `WiringConfiguration` 自动 wiring，端点用 `Depends(Provide[Container.xxx_service])` 取依赖。

- `vision_client` / `scorer` / `readiness_service` 为 `Singleton`（有状态/有缓存/全局共享）；其余 service 为 `Factory`。
- **Scorer 是全系统唯一会演化的绑定点**：容器里 `scorer = providers.Singleton(LocalDirectScorer, ...)` 这一行换成 `CloudRelayScorer` 即切到云端中转，controller/service 一行不改（见 architecture.md）。

### 2.4 启动与就绪态

启动时序：`main.py` → `create_app()`（`app.py`）建容器并 wiring → FastAPI `lifespan` 启动后台预热线程。**启动即一次性加载全部模型**（eager，不静默降级）。

`ReadinessService` 是一个状态机，预热期间不阻塞服务，状态经 `/health` 暴露：

| 字段 | 含义 |
| :-- | :-- |
| `status` | `loading`（预热中）/ `ready`（可服务）/ `error`（失败） |
| `detail` | 失败原因 |
| `retryable` | `error` 是否可重试 |
| `first_run` | 预热前模型缓存是否为空（用于前端区分「首次下载」与「常规加载」） |
| `progress` | `{current, total, step}`，逐模型报进度 |

两类失败的区分（对应「缺失依赖不允许运行」）：

- **依赖缺失**（`DependencyMissing`，Python 包未装）→ `retryable=false`，**致命、不允许运行**，重试无用。
- **权重下载/加载失败**（多为网络）→ `retryable=true`，`POST /warmup/retry` 可重新预热。

预热逐项执行 `VisionClient.warmup_steps()` 返回的 `[(步骤名, 加载函数)]`（共 6 项，覆盖分组 + 层①全部模型），每完成一项更新 `progress`。

### 2.5 模型与缓存

`VisionClient` 线程安全懒加载并缓存模型；启动前把各框架缓存目录统一固定到 Keeper 自己的目录（不污染系统全局、可复现）。

| 模型 | 用途 | 落盘位置（默认 `~/.keeper/models/`） |
| :-- | :-- | :-- |
| DINOv2 | 分组语义特征 | `huggingface/hub/` |
| InsightFace `buffalo_l` | 人脸检测/关键点/识别 | `insightface/` |
| TOPIQ-nr / TOPIQ-nr-face / CLIP-IQA+ | 画质/美学（含 CLIP backbone） | `torch/hub/` |

- 所有本地资源统一在数据根 `~/.keeper`（`KEEPER_HOME` 覆盖）下，子路径派生（`models/`、`thumbnails/`、`keeper.db`、`ark_key`）。设备默认 CPU（桌面最稳），`KEEPER_DEVICE=cuda` 走 CUDA；pyiqa 在 MPS 易炸，固定不走 MPS。
- **DINOv2 选 v2 不选 v3**：v2 是 Apache-2.0、免门禁、商用干净。
- ⚠️ **InsightFace `buffalo_l` 仅限非商用研究**（含层①用到的检测/关键点子模型）。层①只加载「检测 + 68 关键点」；分组另用「检测 + 识别」实例取人脸身份 embedding。**付费产品商用前需替换或单独授权整个包**。

### 2.6 分组逻辑（`grouping_service`）

把相似连拍聚成「瞬间组」。综合相似度由三路信号相乘：

```
综合相似度 = 语义余弦(DINOv2) × 时间衰减(EXIF) × 人脸因子(ArcFace)
距离 = 1 − 综合相似度 → complete-linkage 层次聚类（scipy），按阈值切分
```

- **语义**：DINOv2 归一向量点积（余弦）。
- **时间**：EXIF 拍摄时间差的指数衰减（`exp(-Δt/τ)`，τ=120s）；任一张无时间则因子=1。
- **人脸**：两张照片各取**全部主要人脸**的身份向量集合，用**双向最近邻匹配的平均余弦**衡量「是不是同一拨人」（多人合影也适用），线性映射到 `[floor, 1]`——同一拨人≈1（不干预）、不同人压到 floor（强制拆开）、任一张无脸则=1。专治「同场景、同时间但不同人」被误聚。
- 阈值（`GROUP_DISTANCE_THRESHOLD`、`FACE_SAME_COS`/`FACE_DIFF_COS`/`FACE_FACTOR_FLOOR` 等）是文件顶部的可调旋钮，需在真实照片上标定。

### 2.7 层①本地评分（`prescreen_service`）

对组内每张打 0–100 技术质量分（不做硬拒，硬阈值交给漏斗）：

```
base = 0.45·TOPIQ + 0.20·CLIP-IQA+ + 0.35·主体锐度(归一)   → 0–100
再按「闭眼 / 人脸脱焦 / 欠过曝 / 画面单调 / 观感平庸」等扣分；最高优先级的一条作可解释 reason
```

- **技术质量**：主脸够大用 TOPIQ-nr-face（人像更贴合），否则用通用 TOPIQ-nr；小脸/检不到脸回退整图。
- **主体锐度**：优先用人脸框内拉普拉斯方差，无脸时回退显著区（`cv2.saliency`）/中心区。
- **闭眼**：68 关键点算 EAR；点序异常返回 None 按未知处理。
- 全部阈值集中在文件顶部，用 `mise run localscore` 在真实照片上看分项标定。

### 2.8 层②大模型打分（`scoring_service` + `client/scorer`）

对层①幸存者：生成低清预览 → `Scorer` 打分 → 漏斗 + PK 组装。

- **照片不出本地**：只上传 `imaging.make_preview` 生成的低清 JPEG（长边压到 ~896、≤512KB），用完即焚。
- `LocalDirectScorer.score(previews, model)`：并发调火山 Ark（OpenAI 兼容），提示词在 `client/prompts/layer2_score.md`（不改代码即可迭代），失败重试一次；`parse_response` 从回复抽 `{score, reason, flaws}` 并 clamp。
- 大模型不可用（缺 key/网络/解析失败）抛 `ScorerError` → 端点 502，**不静默降级**。
- `model` 为调用参数：`req.model or settings.ark_model`。

### 2.9 漏斗与保底数

两层共用 `FunnelService.apply_funnel(scored, n)`：**≥60 全过、不足保底数按分补、输入不足全放行**（`通过数 = min(K, max(达标数, n))`）。`ParamsService`：`N = max(ceil(总数×20%), 3)`、`M = ceil(1.5N)`。`converter/score_converter` 给结果标注 `passed`/`quota_fill` 来源供前端透明展示。**规则细节以 [product-flow.md](product-flow.md) 为准。**

### 2.10 HTTP API 契约

服务只绑 `127.0.0.1:8761`（`--port` 改），CORS 仅放行 localhost / `tauri://localhost`。端点在 `controller/*`，前端镜像在 `apps/desktop/src/api.ts`——**改任一端两边都要同步**。

| 端点 | 作用 | 备注 |
| :-- | :-- | :-- |
| `GET /health` | 就绪态 + 进度 | 返回 `status/detail/retryable/first_run/progress/version` |
| `POST /warmup/retry` | 重新预热 | 仅「可重试的 error」生效 |
| `GET /thumbnail?path=&size=` | 缩略图 JPEG | sidecar 解码（含 RAW/HEIC）+ 磁盘缓存；失败 404 |
| `POST /group` | 分组 | 需 `ready`，否则 503；单张失败记 `errors` |
| `POST /assess` | 层①评分 + 收口 survivors | 需 `ready`，否则 503 |
| `POST /score` | 层②打分 + 组装 PK | 不依赖本地模型；大模型不可用 502 |

容错约定：批量端点**单张读图失败记入 `errors` 不中断**；本地模型整体不可用 503、大模型不可用 502——一律显式报错。

---

## 3. 前端 desktop

### 3.1 技术栈与结构

Tauri 2.x（Rust 壳）+ Vue 3 `<script setup>` + TypeScript + Vite + Pinia。

```
src-tauri/src/lib.rs   Rust 壳命令：import_photos（扫目录）/ archive_decisions（写回）
src/api.ts             sidecar HTTP 客户端（fetch，基址可由 VITE_SIDECAR_URL 覆盖）
src/stores/
  engine.ts            引擎连接态 + 就绪态（health/phase + ready/firstRun/canRetry + refresh/retry）
  library.ts           照片库/分组/层①评分/擂台裁决/归档 状态
src/components/
  SplashView.vue       模型加载首屏
  Arena.vue            A/B 擂台
src/App.vue            根：首屏 ↔ 工作区切换 + 工作区 UI
src/styles.css         全局设计系统（见 3.4）
```

### 3.2 Rust 壳与文件系统边界

**文件系统访问只在 Rust 壳**，前端碰不到 FS：

- `import_photos`：弹目录选择器，扫描图片/RAW 扩展名，返回绝对路径列表。
- `archive_decisions`：把擂台终选写回——winners/losers 复制/移动到源目录子文件夹，并写 `keeper-selection.json` 清单；跨设备 rename 失败回退复制+删除。

前端经 `@tauri-apps/api` 的 `invoke` 调这些命令；其余（缩略图、分组、评分）走 localhost HTTP 调 sidecar。

### 3.3 状态流转

```
启动 → 轮询 /health
  未就绪 → SplashView（加载进度 / 重试 / 致命 / 重连）
  就绪：
    常规加载（first_run=false）→ 展示「已就位」后自动进入应用
    首次下载（first_run=true）→ 出现「开始选片」按钮，用户点击进入
进入应用 → 导入目录（Rust 扫图 + sidecar 分组）
  → 每组「评分」（/assess，幸存者高亮）
  → 「进擂台」（Arena 擂主守擂法两两对决，用户终选，可整组舍弃）
  → 「归档」（复制 / 移动 / 仅清单，调 archive_decisions 写回）
```

`engine` store 轮询 `/health`，加载期间 800ms 刷新以更新进度；`ready` 或不可重试的 `error` 即停。

### 3.4 设计系统（`styles.css`）

「暗房 Darkroom」视觉：暖调炭黑背景（暗房氛围）+ 琥珀金强调（胶片/相纸暖光）+ 胶片颗粒纹理 + 取景器框装饰。字体：标题 Fraunces（衬线、编辑气质）、正文 Hanken Grotesk、等宽 DM Mono（via Google Fonts，中文降级系统字体）。语义色：**绿=留下、红=舍弃**。设计 token（CSS 变量）与通用 `.btn` 类集中在此，组件用 scoped style 补充。

---

## 4. 跨切面原则

| 原则 | 落地 |
| :-- | :-- |
| **照片不出本地** | 原图只本地读取；仅低清预览临时上传给层②打分，用完即焚 |
| **不静默降级** | 依赖缺失/模型加载失败/大模型不可用一律抛异常（`VisionUnavailable`/`DependencyMissing`/`ScorerError`），经状态码或就绪态显式上报 |
| **机器不替用户淘汰** | 机器只「为每组递候选」，最终留谁/是否整组舍弃由用户在擂台决定 |
| **API key 本地管理** | 存 `~/.keeper/ark_key`（0600）或环境变量，绝不入库 |
| **配置可复现** | 工具链版本钉死；模型缓存固定到 Keeper 自有目录 |

### 环境变量速查

| 变量 | 作用 |
| :-- | :-- |
| `VITE_SIDECAR_URL` | 前端覆盖 sidecar 基址（默认 `http://127.0.0.1:8761`） |
| `KEEPER_HOME` | 统一数据根（默认 `~/.keeper`）；子路径派生 |
| `KEEPER_HOST` / `KEEPER_PORT` | 服务监听地址/端口 |
| `KEEPER_DEVICE` | `cpu`（默认）/ `cuda`；不走 MPS |
| `KEEPER_DINO_MODEL` / `KEEPER_FACE_PACK` | 切分组/人脸模型（默认 `facebook/dinov2-small` / `buffalo_l`） |
| `ARK_API_KEY` | 大模型 key（或写入 `~/.keeper/ark_key`，0600） |
| `KEEPER_ARK_MODEL` / `KEEPER_ARK_BASE_URL` / `KEEPER_ARK_CONCURRENCY` | Ark 模型 id / 基址 / 并发 |
