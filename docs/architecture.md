# 架构设计

## 总览（MVP：纯本地，无云端）

```
┌──────────────────── Tauri 桌面应用（用户本地机器）────────────────────┐
│                                                                        │
│  前端  Vue 3 + TypeScript + Vite + Pinia（UI / 画廊 / A/B 擂台）       │
│    │                                                                   │
│    │ Tauri IPC                                                         │
│    ▼                                                                   │
│  Rust 壳（Tauri 2.x）                                                  │
│    · 文件系统访问：扫描照片目录、解码 RAW、读写 winners/losers          │
│    · 本地状态持久化                                                     │
│    · 以 sidecar(externalBin) 方式拉起 / 调度 Python 推理服务           │
│    │                                                                   │
│    │ localhost HTTP（127.0.0.1）                                       │
│    ▼                                                                   │
│  Python sidecar（FastAPI）                                             │
│    · 分组：DINOv2 语义 + 拍摄时间 + 人脸聚类                           │
│    · 层① 本地评分漏斗：CV / 人脸 / IQA 打 0–100，≥60 全进、补足 M      │
│    · 层② Scorer 打分漏斗：低清预览打 0–100，≥60 全进、补足 N           │
│        └─ LocalDirectScorer ── 直连大模型 API ──┐                      │
│                                                  │ 只传低清预览         │
└──────────────────────────────────────────────────┼────────────────────┘
                                                    ▼
                                       大模型（火山 Ark / VLM，OpenAI 兼容）
                                       原图永不离开本地；预览推理完即焚
```

## 组件职责边界

### 前端（apps/desktop/src）
纯 UI 与交互：导入目录、展示分组、缩略图画廊、大图查看、A/B 擂台、进度展示。不碰文件系统、不碰推理——一切经 Tauri IPC 走壳层。

### Rust 壳（apps/desktop/src-tauri）
- 唯一能直接访问用户文件系统的层：扫描照片、解码 RAW、归档（winners/losers）、读写本地进度。
- 管理 Python sidecar 生命周期（启动/健康检查/关闭）。
- 把前端请求转成对 sidecar 的 localhost 调用。

### Python sidecar（sidecar/keeper_engine）
重计算与推理。无状态服务：输入图片路径/预览，输出分组、本地分、大模型分。两层级联漏斗（规则详见 [product-flow.md](product-flow.md)，代码里抽象成可复用的 `apply_funnel(scores, n)`：≥60 全进、不足保底数则按分补够、输入不足保底数时全放行）：
- 分组：DINOv2 语义特征 + 拍摄时间 + 人脸聚类
- 层① 本地评分漏斗：锐度 / 曝光 / 熵 / 人脸 / IQA 美学合成 0–100 分，按保底数 `M = ceil(1.5N)` 过滤
- 层② 大模型打分漏斗：封装在 `Scorer` 接口之后，按基础保底数 `N` 过滤

## Scorer 接口：今天直调，明天接云

「给候选打分」是唯一会演化（本地直调 → 云端中转）的环节，所以单独抽象：

```python
class Scorer(Protocol):
    def score(self, previews: list[Preview]) -> list[Score]:
        """对一组候选预览打 0–100 分，返回分数 + 可解释理由。"""

class LocalDirectScorer:   # 本版：sidecar 直连大模型 API
    ...

class CloudRelayScorer:    # 未来商业版：调自建云端中转层（鉴权/计量/加价）
    ...
```

业务流程只依赖 `Scorer` 协议。商业化时新增 `CloudRelayScorer` 实现并切换配置即可，**编排逻辑零改动**。

## 数据流：什么离开本地，什么不离开

| 数据 | 是否离开本地 | 说明 |
| :-- | :-- | :-- |
| 原图（含 RAW） | **永不** | 只被本地 sidecar 读取 |
| 分组 / 本地分 / 评分结果 | **永不** | 全在本地算 |
| 候选的低清预览 | 仅打分时临时上传 | 用完即焚，不落盘 |
| 选片结果（winners/losers） | **永不** | 写回用户磁盘 |
| API key | **永不入库** | 本地 `~/.config/keeper/`，0600 |

## 持久化（MVP）

采用「单文件夹单会话」思路：进度、分组、PK 状态写在用户照片目录下的本地状态文件，支持中断续做，由 Rust 壳负责读写。具体格式在实现阶段定。

## 未来云端层（不在本 MVP）

商业化时新增一层云端中转/计费服务（建议 Go 或 Python FastAPI）：鉴权（JWT）、用量计量、加价差、配额限流、调大模型、支付。届时桌面端的 `LocalDirectScorer` 换成 `CloudRelayScorer` 指向该服务，其余不变。
