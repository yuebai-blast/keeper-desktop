"""层② 大模型打分端点：对层① survivors 生成低清预览上云打分，组装 PK 候选集。"""

from __future__ import annotations

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from ..container import Container
from ..request.score_request import ScoreRequest
from ..response.score_response import ScoreResponse
from ..service.scoring_service import ScoringService

router = APIRouter()


@router.post("/score", response_model=ScoreResponse)
@inject
def score(
    req: ScoreRequest,
    svc: ScoringService = Depends(Provide[Container.scoring_service]),
) -> ScoreResponse:
    """照片不出本地：只上传低清预览。大模型不可用（缺 key / 网络）整体 502——不静默降级。"""
    return svc.score(req)
