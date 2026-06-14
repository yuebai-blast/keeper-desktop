"""层① 本地评分端点编排：逐张打分 → 漏斗（保底数 M）收口出 survivors。

模型未就绪（预热中/失败）直接 503，不傻等也不假装健康；
单张数据错误（文件损坏等）记入 errors、不中断。
"""

from __future__ import annotations

from fastapi import HTTPException

from ..converter import score_converter
from ..exception.errors import VisionUnavailable
from ..request.assess_request import AssessRequest
from ..response.assess_response import AssessResponse
from ..response.common import PhotoError
from ..vo.local_score import LocalScore
from .funnel_service import FunnelService
from .params_service import ParamsService
from .prescreen_service import PrescreenService
from .readiness_service import ReadinessService


class AssessService:
    """/assess 编排：就绪门禁 + 逐张评分容错 + 漏斗收口（M）+ 组装响应。"""

    def __init__(
        self,
        prescreen: PrescreenService,
        readiness: ReadinessService,
        funnel: FunnelService,
        params: ParamsService,
    ) -> None:
        self._prescreen = prescreen
        self._readiness = readiness
        self._funnel = funnel
        self._params = params

    def assess(self, req: AssessRequest) -> AssessResponse:
        if self._readiness.status != "ready":
            raise HTTPException(
                status_code=503,
                detail=f"模型未就绪（{self._readiness.status}）：{self._readiness.detail or '预热中，请稍后重试'}",
            )
        scores: list[LocalScore] = []
        errors: list[PhotoError] = []
        for photo in req.photos:
            try:
                scores.append(self._prescreen.assess_photo(photo.path, photo.companions))
            except VisionUnavailable as e:
                raise HTTPException(status_code=503, detail=f"本地模型不可用：{e}") from e
            except Exception as e:  # noqa: BLE001 —— 单张数据错误上报而非静默跳过
                errors.append(PhotoError(path=photo.path, error=f"{type(e).__name__}: {e}"))

        n = self._params.compute_n(len(req.photos))
        m = self._params.compute_m(n)
        survivors = score_converter.to_survivors(self._funnel.apply_funnel(scores, m))
        return AssessResponse(
            group_id=req.group_id, scores=scores, survivors=survivors, n=n, m=m, errors=errors
        )
