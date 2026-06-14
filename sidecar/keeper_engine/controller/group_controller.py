"""分组端点：把相似连拍聚成「瞬间组」（DINOv2 语义 × 时间 × 人脸身份）。"""

from __future__ import annotations

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from ..container import Container
from ..request.group_request import GroupRequest
from ..response.group_response import GroupResponse
from ..service.grouping_service import GroupingService

router = APIRouter()


@router.post("/group", response_model=GroupResponse)
@inject
def group(
    req: GroupRequest,
    svc: GroupingService = Depends(Provide[Container.grouping_service]),
) -> GroupResponse:
    """模型未就绪直接 503；单张读图失败记入 errors、不中断；其余照片照常分组。"""
    return svc.group(req)
