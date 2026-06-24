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

数据流、Scorer 可替换设计、未来云端中转的插入点，详见 [docs/architecture.md](docs/architecture.md)。工程实现细节（分层、DI、就绪态、各部分算法、API 契约）详见 [docs/tech-overview.md](docs/tech-overview.md)。

### 本地推理为什么是独立的 Python sidecar

分组（DINOv2）、人脸（InsightFace）、美学/质量（pyiqa）、传统 CV 这些本地推理的生态全在 Python。打包时用 PyInstaller 把 Python 服务冻结成 onedir 目录，经 Tauri `bundle.resources` 随应用分发，Rust 壳从 resource 路径用 `std::process` 拉起，前端经 localhost HTTP 调用它（不用 externalBin——它只认单文件，承载不了 onedir，见 docs/packaging.md）。

### Scorer 可替换：今天直调，明天接云

「给候选打分」抽象为 `Scorer` 接口，业务流程只依赖接口：

- `LocalDirectScorer`（本版）：sidecar 直连大模型 API（火山 Ark，OpenAI 兼容协议）。
- `CloudRelayScorer`（未来商业版）：改调自建云端中转层（鉴权 + 计量计费 + 加价）。

商业化时只需新增实现，并在 DI 容器（`keeper_engine/container.py`）里改 `scorer` 这一行绑定，**业务流程（controller/service）一行不改**。

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

服务只绑 `127.0.0.1`，默认端口 **8761**（`mise run sidecar -- --port` 改），前端经 `VITE_SIDECAR_URL` 覆盖基址。CORS 仅放行 localhost / `tauri://localhost`。端点定义在 `sidecar/keeper_engine/controller/*`（经 DI 注入 service），前端客户端镜像在 `apps/desktop/src/api.ts`——**改任一端的请求/响应结构，两边都要同步**。

**鉴权约定**：prod 模式下 Tauri 壳启动时生成随机 token 并经 `KEEPER_AUTH_TOKEN` env 注入 sidecar；所有端点均需鉴权——JSON 端点从请求头 `X-Keeper-Token` 读取，`/thumbnail` 从 query 参数 `token` 读取；鉴权失败返回纯 HTTP 401（不包 ApiResponse），前端收到 401 后合成 `ApiError(110003, "AUTH_FAILED")`。dev/独立运行时 `KEEPER_AUTH_TOKEN` 留空则不鉴权，方便本地调试。此外 `/thumbnail` 仅放行 `workspace_dir` 内的路径，请求超出范围返回 404。

**统一响应包装（全局规范）**：所有 JSON 端点**恒返回 HTTP 200**，业务成败由响应体 `ApiResponse{code,data,msg}` 的 `code` 表达（`0`=成功）。成功响应由各 controller 的 `EnvelopeRoute`（`response/envelope.py`）自动包成 `{code:0,data:<原返回>,msg:null}`，controller 代码不变；异常由 `app.py` 注册的处理器按 `BizCode`（`enumeration/biz_code.py`）统一翻译成 `{code,data:null,msg}`。业务码为 6 位、前两位分段（`11`通用/`21`本地模型/`31`大模型/`41`项目工作流）。**例外**：`GET /thumbnail` 返回二进制 JPEG，豁免包装（解码失败仍用原生 404）。前端 `api.ts` 的 `get/post` 自动解包 `data`，`code!==0` 抛 `ApiError(code,msg)`；`BizCode` 常量在两端各存一份镜像，**改任一端两边同步**。下表「门禁」列写的是失败时返回的业务码。

| 端点 | 作用 | 门禁（失败业务码） |
| :-- | :-- | :-- |
| `GET /health` | 存活 + 层①模型就绪态（`loading`/`ready`/`error`），后台预热线程更新 | — |
| `GET /thumbnail?path=&size=` | sidecar 解码（含 RAW/HEIC）并缩放出 JPEG；就近缓存于原图同目录 `.thumbnails/{stem}@{size}.jpg`（副本不可变，无需失效判断）；只走 localhost；**二进制豁免 ApiResponse** | — |
| `POST /group` | 把照片路径聚成「瞬间组」 | 需 `ready`，否则 `MODEL_NOT_READY` |
| `POST /assess` | 层①本地评分 + 漏斗收口出 survivors | 需 `ready`，否则 `MODEL_NOT_READY` |
| `POST /score` | 层②大模型打分 + 组装 PK 候选集 | 不依赖本地模型，缺 key/网络 → `SCORER_FAILED` |

容错约定：批量端点对**单张读图失败记入 `errors` 不中断**；本地模型整体不可用（预热失败/缺依赖）才抛 `MODEL_NOT_READY`/`MODEL_DEPENDENCY_MISSING`，大模型不可用才抛 `SCORER_FAILED`——一律显式报错，不静默降级。

> 上面 5 个是**无状态推理端点**（直收路径、即算即返）。下面是**项目工作流端点**——状态持久化在 sidecar（sqlite），是桌面端选片流程的主接口。

### 项目工作流端点（`controller/project_controller.py`，前缀 `/projects`）

选片以**项目**为单位（名字唯一，输出到 `~/Pictures/Keeper/{项目名}`），每步持久化、可随时退出恢复。

| 端点 | 作用 | 门禁 |
| :-- | :-- | :-- |
| `POST /projects/preview` | 扫描源文件夹：数量 / 拍摄时间范围 / 拍摄地（不建项目） | — |
| `POST /projects` | 建项目 + **递归**收图、复制副本到 `{KEEPER_HOME}/workspace/{名}` 并改名为随机 UUID（扁平、回避重名；不动源）。DB 存原始相对路径，完成时据此还原原始目录树+原名 | 名重复→`PROJECT_NAME_DUPLICATE` |
| `GET /projects` · `GET /projects/{id}` | 项目列表 / 项目详情（含各组摘要） | 不存在→`PROJECT_NOT_FOUND` |
| `DELETE /projects/{id}` | 删项目：清 workspace 副本 + 全部 DB 资源（照片/组/PK/项目行）；不动源与已完成项目输出目录 | 不存在→`PROJECT_NOT_FOUND` |
| `POST /projects/{id}/group` | 分组并落库（写 group_key + 建组、聚合拍摄地/时间） | 需 `ready`→`MODEL_NOT_READY` |
| `GET /projects/{id}/groups/{gk}` | 组详情：照片 + 两层评分 + 去留 + PK 进度 | 不存在→`GROUP_NOT_FOUND` |
| `POST /projects/{id}/groups/{gk}/assess` | 层①+层②评测、初始化去留；已评测则原样返回 | `ready`→`MODEL_NOT_READY`，层②→`SCORER_FAILED` |
| `POST …/{gk}/selection` · `…/{gk}/confirm` | 改去留/救回标记 · 确认本组（标识，可改回） | — |
| `POST …/{gk}/pk/start` · `…/pk/choose` · `…/pk/undo` | PK 擂台：起/选（四结局）/撤销，每步落库 | — |
| `POST /projects/{id}/confirm-all` | 一键通过：未评测组先评测，再全部确认 | `ready`→`MODEL_NOT_READY`，层②→`SCORER_FAILED` |
| `GET /projects/{id}/review` | 跨组拍平的去留结果（kept/discarded 两区，含 is_junk），供最终预览页 | 不存在→`PROJECT_NOT_FOUND` |
| `POST /projects/{id}/selection` | 二次预览页批量改去留（项目级，区别于组内 `/groups/{gk}/selection`） | 不存在→`PROJECT_NOT_FOUND` |
| `POST /projects/{id}/complete` | 完成前需经最终预览页。复制「通过」到目标目录 + 删 workspace + 标记完成 | 全组确认才放行，否则 `GROUPS_NOT_ALL_CONFIRMED` |

## 分层与漏斗管线模块地图（最关键逻辑）

sidecar 按 Spring Boot 式分层 + 依赖注入组织（容器 `keeper_engine/container.py`）：
`controller`（路由，只接线）→ `service`（业务/编排）→ `client`（外部依赖：本地模型 / 大模型）。
配置在 `config/settings.py`（收口所有环境变量），出入参在 `request`/`response`，值对象在 `vo`，
枚举/异常/转换在 `enumeration`/`exception`/`converter`，纯函数工具在 `util`（影像 IO、CV 信号）。
统一响应包装在 `response/api_response.py`（`ApiResponse{code,data,msg}`）+ `response/envelope.py`（`EnvelopeRoute` 自动包成功响应 + `install_exception_handlers` 把领域异常按 `enumeration/biz_code.py` 的 `BizCode` 翻译成 HTTP 200）；service 中断用 `raise BizException(BizCode.X)`。
入口 `main.py`（uvicorn）→ `app.py`（建容器、CORS、注册异常处理器、lifespan 启动预热、注册各 controller）。

数据流：分组 → 层①逐张打分 → 层②大模型打分 + 组 PK。关键模块：

- `service/grouping_service.py` — 把相似连拍聚成「瞬间组」。综合相似度 = 语义余弦(DINOv2) × 时间衰减(EXIF) × 人脸因子(ArcFace 人脸集合，双向最近邻平均余弦，多人合影也适用），专门把「同场景、同时间但不同人」拆成不同组；任一张无脸则因子=1。`cluster` 为静态纯算法便于单测；阈值在文件顶部，**在真实人脸上标定**。
- `service/funnel_service.py` — **全系统最关键**。`FunnelService.apply_funnel(scored, n)` 是两层通用筛选规则（≥60 全过、不足保底数按分补、输入不足全放行）。改它影响整个产品行为。
- `service/params_service.py` — 保底数：`N = max(ceil(总数×20%), 3)`（层②），`M = ceil(1.5×N)`（层①）。
- `service/prescreen_service.py` — 层①合成分（TOPIQ + CLIP-IQA+ + 主体锐度，再按闭眼/脱焦/曝光等扣分）；阈值集中在文件顶部，**在真实照片上标定**。
- `service/ranking_service.py` + `converter/score_converter.py` — 层②出口：套漏斗 + 给候选标注 passed/quota_fill 来源，组装 PK。
- `service/{assess,scoring,readiness}_service.py` — 三个端点编排：层①评分收口 / 层②打分组装 / 模型预热与就绪态。
- `service/project_service.py` — **项目工作流编排核心**：预览/建项目/分组/评测/裁决/确认/完成，复用上面所有引擎 service，把结果落库（持久化权威）。`service/pk_service.py` — PK 擂台状态机（四结局，状态存 `PkState`，每步可恢复），终止时把去留写回 `ProjectPhoto.selection`。`service/workspace_service.py` — workspace 文件操作：**递归**扫描源图、复制副本时改名为 `{uuid}{原扩展名}`（扁平、回避跨目录/异扩展名重名）、完成时按相对路径 `restore_tree` **还原原始目录树+原名**、清理。**只动副本与输出目录，不碰源**。
- 持久化层（sqlite）：`config/database.py` 共享 engine（全部 mapper 复用，`create_all` 在 app 启动时建表）；`entity/*` 实体（`Project`/`ProjectPhoto`/`PhotoGroup`/`PkState`/`GeocodeCache`/`ModelModule`）+ `mapper/*` 数据访问。层②/层①评分明细以 JSON 列就地存在 `ProjectPhoto`。
- `client/geocode_client.py` — 拍摄地在线反查地名（只发 GPS 坐标、不发照片，默认 OSM Nominatim，结果缓存到 `GeocodeCache`）；GPS 读取在 `util/imaging.read_gps`。
- `client/vision_client.py` — 本地模型懒加载（DINOv2 / InsightFace / pyiqa），DI Singleton。模型缓存目录取 `KEEPER_MODELS_DIR`（prod 为 `app_cache_dir/models`，dev 默认 `{KEEPER_HOME}/models`）。层①只用检测+关键点；分组另用「检测+识别」实例取人脸身份。⚠️ 识别模型（ArcFace，`buffalo_l`）仅限非商用研究，**商用前需替换或授权**（对整个 `buffalo_l` 包适用，含层①的检测/关键点）。
- `client/scorer.py` — `Scorer` 协议 + `LocalDirectScorer`（直连火山 Ark），提示词在 `client/prompts/layer2_score.md`（不改代码即可迭代）。层② 额外输出 `is_junk`（非摄影杂图标记：截图/地图/纯色/聊天记录等），纯标记不影响去留，落库到 `ProjectPhoto.llm_is_junk`、供最终预览页一键清理。**容器里 `scorer` 一行绑定即可切 `CloudRelayScorer`，业务流程不动。**

桌面端：扫描、读 EXIF、复制副本、归档、删除等**文件操作已下沉到 sidecar**（Python，统一管 `{KEEPER_HOME}` 数据根）。Rust 壳（`src-tauri/src/lib.rs`）只保留需要原生 GUI 的命令：`pick_folder`（目录选择对话框）、`open_path`（打开输出目录）、`exit_app`。前端用 **vue-router** 多页流程（`pages/*`：项目主页 / 新建 / 分组列表 / 组详情 / 完成），状态在 Pinia（`engine` 连接态、`projects` 项目/组/PK——权威在 sidecar，前端每步操作后用服务端返回刷新）；`api.ts` 镜像上面两类端点。

## 环境变量速查

| 变量 | 作用 |
| :-- | :-- |
配置集中在 `config/settings.py`（pydantic-settings），可配项从 `{KEEPER_HOME}/config.toml` 与 `KEEPER_*` 环境变量加载（环境变量优先），子路径全部派生自数据根 `KEEPER_HOME`（prod 见下表 KEEPER_HOME 行，dev 默认 `~/.keeper`）。

| 变量 | 作用 |
| :-- | :-- |
| `VITE_SIDECAR_URL` | 前端覆盖 sidecar 基址（默认 `http://127.0.0.1:8761`） |
| `KEEPER_HOME` | 统一数据根：prod 由 Tauri 壳注入为 OS 约定目录（macOS `~/Library/Application Support/club.mint-ai.keeper`），dev 未注入时回落 `~/.keeper`。下含 `workspace/`（项目副本，含各项目就近的 `.thumbnails/` 缩略图缓存）、`keeper.db`、`ark_key`、`volc_ak`/`volc_sk`（管理面 AK/SK，0600） |
| `KEEPER_MODELS_DIR` | 模型缓存目录；prod 由 Tauri 注入为 `app_cache_dir/models`（大缓存不进用户备份），dev 默认 `{KEEPER_HOME}/models` |
| `KEEPER_AUTH_TOKEN` | sidecar HTTP 鉴权 token；prod 由 Tauri 启动时生成并经 env 注入，dev/独立运行留空=不鉴权 |
| `KEEPER_OUTPUT_ROOT` | 选片完成输出根（默认 `~/Pictures/Keeper`），最终输出到 `{此}/{项目名}` |
| `KEEPER_GEOCODE_ENABLED` / `KEEPER_GEOCODE_URL` | 拍摄地反查开关 / 服务地址（默认 OSM Nominatim，只发坐标） |
| `KEEPER_DEVICE` | `cpu`（默认最稳）/ `cuda`；pyiqa 在 MPS 易炸，固定不走 MPS |
| `KEEPER_DINO_MODEL` / `KEEPER_FACE_PACK` | 切分组/人脸模型（默认 `facebook/dinov2-small` / `buffalo_l`） |
| `ARK_API_KEY` | 大模型 key（推理面）；也可写入 `{KEEPER_HOME}/ark_key`（0600），绝不入库 |
| `KEEPER_ARK_MODEL` / `KEEPER_ARK_BASE_URL` / `KEEPER_ARK_CONCURRENCY` | Ark 模型 id / 基址 / 并发数 |
| `VOLCENGINE_ACCESS_KEY` / `VOLCENGINE_SECRET_KEY` | 火山「管理面」AK/SK，**仅**用于设置页「拉取视觉模型」（`POST /settings/models` 调 `ListFoundationModels`），与打分无关；也可写入 `{KEEPER_HOME}/volc_ak`·`{KEEPER_HOME}/volc_sk`（0600），绝不入库 |
| `KEEPER_VOLC_REGION` | 管理面地域（默认 `cn-beijing`，火山方舟管理面当前仅此地域） |

## 关键约定

- **依赖来源**：sidecar 在 `sidecar/pyproject.toml` 声明、`uv.lock` 锁定；改完跑 `mise run install`。前端在 `apps/desktop/package.json`。
- **工具链钉死**：`[tools]` 里所有版本必须是具体版本号，禁止 `latest`，保证可复现。新增工具/命令一律沉淀到 `mise.toml`，不散落到零散脚本。
- **OpenCV 三包冲突**：`sidecar/pyproject.toml` 的 `[tool.uv] override-dependencies` 用「marker 永假」把 `opencv-python(-headless)` 从依赖树剔除，保住 `opencv-contrib-python` 的 `cv2.saliency`。别把它们加回依赖。
- **不静默降级**：本地推理依赖缺失或模型加载失败立刻抛异常，不悄悄退化。
- **API key 本地管理**：大模型 key 存在 `{KEEPER_HOME}/ark_key`（0600 权限），可由 UI 录入或环境变量注入，绝不入库。火山管理面 AK/SK 同款处理（各一个 0600 文件、env 可覆盖、绝不入库）——机密一律隔离存文件，不进 sqlite（避免随 DB 备份/分享外泄）。
- **照片不出本地**：任何把原图发往网络的改动都违反核心原则；只有低清预览允许上传给打分服务，以及拍摄地反查只发 GPS 坐标。复制副本/归档/删除只动 `{KEEPER_HOME}/workspace` 与输出目录，绝不写用户源文件夹。
- **中文书写**：CLAUDE.md、README、`docs/`、代码注释、Git 提交信息一律用简体中文；代码标识符/API 名保持英文。

## 进度与尚未落地（按计划推进）

已落地：分组、层①评分、层②大模型打分、PK 候选组装、缩略图缓存。

**项目化选片工作流（sqlite 持久化）已落地**：以项目为单位，源图**递归**复制副本到 `{KEEPER_HOME}/workspace/{名}`（改名为随机 UUID、扁平存放，保护原文件）→ 分组 → 逐组评测（层①+层②，自动分通过/未通过）→ 用户裁决（救回 + A/B 擂台 PK 四结局 + 手动改判 + 确认）→ 完成时把「通过」按原始相对路径**还原目录树+原名**复制到 `~/Pictures/Keeper/{名}` 并清理 workspace。全程每步落库，可随时退出/恢复（见 `service/project_service.py`、`service/pk_service.py`、前端 `pages/*` + `stores/projects.ts`）。拍摄地经 GPS+在线反查展示（尽力而为）。

分组已接入人脸身份（ArcFace 人脸集合相似度）拆开「同场景不同人」，多人合影按「是不是同一拨人」区分。

层② 杂图标记（`is_junk` 截图/地图/纯色/聊天记录等非摄影图片）已落地，纯标记不改去留/分数/漏斗，供最终预览页一键清理。完成前的最终预览页已落地（跨组拍平 kept/discarded 两区，二次去留批量操作、一键勾选杂图、大图浮层）。

尚未落地：
- `CloudRelayScorer`（商业版云端中转，按 `Scorer` 协议新增实现 + 切配置即可，业务流程不改）。
- 拍摄地离线反查（当前在线 Nominatim，断网/失败则不展示，不阻断流程）。
- 大批量导入时的复制/分组进度条（当前同步，量大时前端等待）。
- 各阈值/权重旋钮仍需在真实照片集上标定。
- **商用授权**：`buffalo_l`（含分组用的 ArcFace 识别 + 层①的检测/关键点）仅限非商用研究，商用前必须替换或授权。
