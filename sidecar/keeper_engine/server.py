"""本地推理服务入口（FastAPI）。只监听 127.0.0.1，由 Tauri 壳经 localhost 调用。

启动：mise run sidecar [-- --port 8761]
"""

from __future__ import annotations

import argparse
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import __version__, grouping, imaging, params, prescreen, ranking, vision
from .funnel import apply_funnel
from .models import (
    AssessRequest,
    AssessResponse,
    GroupRequest,
    GroupResponse,
    PhotoError,
    PkOrigin,
    ScoreRequest,
    ScoreResponse,
    SurvivorEntry,
)
from .scorer import LocalDirectScorer, Preview, ScorerError
from .vision import VisionUnavailable

logger = logging.getLogger("keeper_engine.server")


class _Readiness:
    """层① 模型的就绪状态。后台预热线程更新，/health 读取。

    status: loading（预热中）| ready（可服务）| error（加载失败，detail 含原因）。
    """

    def __init__(self) -> None:
        self.status = "loading"
        self.detail = ""


_readiness = _Readiness()


def _warmup() -> None:
    """启动期后台预热：一次性下载+载入层① 全部模型。失败不崩进程，记入就绪状态。

    这样模型在第一个 /assess 之前就备好，且加载失败能在启动期经 /health 暴露——
    既不让首个请求卡几分钟，又不「假装健康」（不静默降级）。
    """
    try:
        vision.require_grouping_capabilities()
        vision.require_layer1_capabilities()
        _readiness.status = "ready"
        logger.info("server: 分组 + 层① 模型预热完成，服务就绪")
    except Exception as e:  # noqa: BLE001 —— 捕获以经 /health 上报，而非让线程静默死掉
        _readiness.status = "error"
        _readiness.detail = f"{type(e).__name__}: {e}"
        logger.error("server: 层① 模型预热失败：%s", _readiness.detail)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 后台预热，不阻塞启动；启动后立刻可应答 /health（报 loading），就绪后转 ready。
    threading.Thread(target=_warmup, name="keeper-warmup", daemon=True).start()
    yield


app = FastAPI(title="Keeper Engine", version=__version__, lifespan=lifespan)

# 桌面端 Tauri webview 经浏览器上下文跨源调用本服务，需放行本地来源。
# 服务只绑 127.0.0.1（仅本机可达），故放行 localhost / tauri 来源是安全的。
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^(https?://(localhost|127\.0\.0\.1)(:\d+)?|tauri://localhost)$",
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    """liveness + 模型就绪态。status 为 loading/ready/error；error 时 detail 含原因。"""
    return {"status": _readiness.status, "version": __version__, "detail": _readiness.detail}


@app.post("/assess", response_model=AssessResponse)
def assess(req: AssessRequest) -> AssessResponse:
    """层① 本地评分：逐张打 0–100 分，再用 apply_funnel(scores, M) 收口出 survivors。

    模型未就绪（预热中/失败）直接 503，不傻等也不假装健康；
    单张数据错误（文件损坏等）记入 errors、不中断。
    """
    if _readiness.status != "ready":
        raise HTTPException(
            status_code=503,
            detail=f"模型未就绪（{_readiness.status}）：{_readiness.detail or '预热中，请稍后重试'}",
        )
    scores = []
    errors: list[PhotoError] = []
    for photo in req.photos:
        try:
            scores.append(prescreen.assess_photo(photo.path, photo.companions))
        except VisionUnavailable as e:
            raise HTTPException(status_code=503, detail=f"本地模型不可用：{e}") from e
        except Exception as e:  # noqa: BLE001 —— 单张数据错误上报而非静默跳过
            errors.append(PhotoError(path=photo.path, error=f"{type(e).__name__}: {e}"))

    n = params.compute_n(len(req.photos))
    m = params.compute_m(n)
    survivors = [
        SurvivorEntry(
            path=s.path, score=s.score,
            origin=PkOrigin.QUOTA_FILL if is_quota_fill else PkOrigin.PASSED,
        )
        for s, is_quota_fill in apply_funnel(scores, m)
    ]
    return AssessResponse(group_id=req.group_id, scores=scores, survivors=survivors, n=n, m=m, errors=errors)


@app.post("/group", response_model=GroupResponse)
def group(req: GroupRequest) -> GroupResponse:
    """分组：把相似连拍聚成「瞬间组」（DINOv2 语义 × 时间邻近）。

    模型未就绪直接 503；单张读图失败记入 errors、不中断；其余照片照常分组。
    """
    if _readiness.status != "ready":
        raise HTTPException(
            status_code=503,
            detail=f"模型未就绪（{_readiness.status}）：{_readiness.detail or '预热中，请稍后重试'}",
        )
    paths, embeddings, times = [], [], []
    errors: list[PhotoError] = []
    for p in req.photos:
        try:
            emb, t = grouping.embed_photo(p)
            paths.append(p)
            embeddings.append(emb)
            times.append(t)
        except VisionUnavailable as e:
            raise HTTPException(status_code=503, detail=f"本地模型不可用：{e}") from e
        except Exception as e:  # noqa: BLE001 —— 单张数据错误上报而非静默跳过
            errors.append(PhotoError(path=p, error=f"{type(e).__name__}: {e}"))

    groups = grouping.cluster(paths, embeddings, times)
    return GroupResponse(groups=groups, errors=errors)


@app.post("/score", response_model=ScoreResponse)
def score(req: ScoreRequest) -> ScoreResponse:
    """层② 大模型打分：对层① survivors 生成低清预览上云打分，再按保底数 N 组装 PK 候选集。

    照片不出本地：只上传 make_preview 生成的低清 JPEG。
    单张读图失败记入 errors；大模型不可用（缺 key / 网络）整体 502——不静默降级。
    本端点只用 imaging + 远程 Ark，不依赖本地模型预热，故不设就绪门禁。
    """
    previews: list[Preview] = []
    errors: list[PhotoError] = []
    for p in req.photos:
        try:
            img = imaging.load_for_analysis(p)
            previews.append(Preview(path=p, jpeg=imaging.make_preview(img)))
        except Exception as e:  # noqa: BLE001 —— 单张数据错误上报而非静默跳过
            errors.append(PhotoError(path=p, error=f"{type(e).__name__}: {e}"))

    try:
        scores = LocalDirectScorer(model=req.model).score(previews)
    except ScorerError as e:
        raise HTTPException(status_code=502, detail=f"层② 大模型打分失败：{e}") from e

    n = params.compute_n(req.group_total)
    pk_set = ranking.assemble_pk_set(req.group_id, scores, n)
    return ScoreResponse(group_id=req.group_id, scores=scores, pk=pk_set.entries, n=n, errors=errors)


# TODO: 后续轮次——/assemble 等编排端点（assemble_pk_set 已可直接复用）；
#       桌面端 A/B 擂台终选与写回。


def main() -> None:
    parser = argparse.ArgumentParser(description="Keeper 本地推理服务")
    parser.add_argument("--host", default="127.0.0.1", help="仅本地，勿绑 0.0.0.0")
    parser.add_argument("--port", type=int, default=8761)
    args = parser.parse_args()

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
