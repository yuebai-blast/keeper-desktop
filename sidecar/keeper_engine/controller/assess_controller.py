"""层① 本地评分端点：逐张打 0–100 分，再用漏斗（保底数 M）收口出 survivors。"""

from __future__ import annotations

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from ..container import Container
from ..request.assess_request import AssessRequest
from ..response.assess_response import AssessResponse
from ..service.assess_service import AssessService

router = APIRouter()


@router.post("/assess", response_model=AssessResponse)
@inject
def assess(
    req: AssessRequest,
    svc: AssessService = Depends(Provide[Container.assess_service]),
) -> AssessResponse:
    """模型未就绪（预热中/失败）直接 503；单张数据错误记入 errors、不中断。"""
    return svc.assess(req)
