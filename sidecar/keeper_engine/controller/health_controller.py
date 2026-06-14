"""健康检查 + 模型加载进度 / 重试端点。"""

from __future__ import annotations

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from .. import __version__
from ..container import Container
from ..service.readiness_service import ReadinessService

router = APIRouter()


@router.get("/health")
@inject
def health(readiness: ReadinessService = Depends(Provide[Container.readiness_service])) -> dict:
    """liveness + 模型就绪态。

    返回 status（loading/ready/error）、detail、retryable（error 是否可重试）、
    first_run（是否首次需下载）、progress（current/total/step 加载进度）。
    """
    return {"version": __version__, **readiness.snapshot()}


@router.post("/warmup/retry")
@inject
def retry_warmup(readiness: ReadinessService = Depends(Provide[Container.readiness_service])) -> dict:
    """重新预热模型——仅在「可重试的 error」时生效（下载失败重试）；返回最新就绪态。"""
    readiness.retry()
    return {"version": __version__, **readiness.snapshot()}
