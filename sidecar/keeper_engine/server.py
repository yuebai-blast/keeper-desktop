"""本地推理服务入口（FastAPI）。只监听 127.0.0.1，由 Tauri 壳经 localhost 调用。

启动：mise run sidecar [-- --port 8761]
"""

from __future__ import annotations

import argparse
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from . import __version__, params, prescreen, vision
from .funnel import apply_funnel
from .models import AssessRequest, AssessResponse, PhotoError
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
        vision.require_layer1_capabilities()
        _readiness.status = "ready"
        logger.info("server: 层① 模型预热完成，服务就绪")
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
    survivors = [s.path for s, _ in apply_funnel(scores, m)]
    return AssessResponse(group_id=req.group_id, scores=scores, survivors=survivors, n=n, m=m, errors=errors)


# TODO: 后续轮次补端点——
#   POST /group     输入照片路径 → 分组（grouping.group_photos）
#   POST /score     输入候选预览 → 层② 大模型 0–100 分（Scorer.score）
#   POST /assemble  输入层② 分数 + N → PK 候选集（ranking.assemble_pk_set）


def main() -> None:
    parser = argparse.ArgumentParser(description="Keeper 本地推理服务")
    parser.add_argument("--host", default="127.0.0.1", help="仅本地，勿绑 0.0.0.0")
    parser.add_argument("--port", type=int, default=8761)
    args = parser.parse_args()

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
