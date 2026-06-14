"""健康检查端点：liveness + 模型就绪态。"""

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
    """liveness + 模型就绪态。status 为 loading/ready/error；error 时 detail 含原因。"""
    return {"status": readiness.status, "version": __version__, "detail": readiness.detail}
