"""层① 本地评分端点编排：组内逐张「并发」打分 → 漏斗（保底数 M）收口出 survivors。

模型未就绪（预热中/失败）直接抛 MODEL_NOT_READY，不傻等也不假装健康；
单张数据错误（文件损坏等）记入 errors、不中断；任一张 VisionUnavailable → 整体 MODEL_NOT_READY。

并发：逐张评分用 ThreadPoolExecutor，并发度由 local_concurrency 决定，**默认 1=串行**。
CPU/MPS 上 torch/onnxruntime 已用 intra-op 多线程吃满核，上层再并发多张图无真实收益、只增
峰值内存与抖动（参考 pianke：MPS/CPU 固定单线程最稳），故默认串行；仅 CUDA 等场景才值得调大。
若开并发：onnxruntime / DINOv2 的 no-grad 前向是只读推理可并发，但 pyiqa（尤其 topiq_nr-face
内部的 facexlib face_helper）有非线程安全的共享可变状态——这由 VisionClient 的 per-model 锁兜底。
结果按输入下标回填，保证与输入同序（survivors/排序不依赖完成顺序）。
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from ..converter import score_converter
from ..enumeration.biz_code import BizCode
from ..exception.errors import BizException, VisionUnavailable
from ..request.assess_request import AssessRequest
from ..response.assess_response import AssessResponse
from ..response.common import PhotoError
from ..vo.local_score import LocalScore
from .funnel_service import FunnelService
from .params_service import ParamsService
from .prescreen_service import PrescreenService
from .readiness_service import ReadinessService


class AssessService:
    """/assess 编排：就绪门禁 + 逐张并发评分容错 + 漏斗收口（M）+ 组装响应。"""

    def __init__(
        self,
        prescreen: PrescreenService,
        readiness: ReadinessService,
        funnel: FunnelService,
        params: ParamsService,
        concurrency: int = 2,
    ) -> None:
        self._prescreen = prescreen
        self._readiness = readiness
        self._funnel = funnel
        self._params = params
        self._concurrency = max(1, concurrency)

    def assess(self, req: AssessRequest, on_progress: Callable[[], None] | None = None) -> AssessResponse:
        if self._readiness.status != "ready":
            raise BizException(
                BizCode.MODEL_NOT_READY,
                f"模型未就绪（{self._readiness.status}）：{self._readiness.detail or '预热中，请稍后重试'}",
            )

        photos = req.photos
        results: list[LocalScore | None] = [None] * len(photos)
        errors: list[PhotoError] = []
        unavailable: VisionUnavailable | None = None

        def work(idx: int) -> None:
            nonlocal unavailable
            photo = photos[idx]
            try:
                results[idx] = self._prescreen.assess_photo(photo.path, photo.companions)
            except VisionUnavailable as e:
                unavailable = e  # 本地模型整体不可用，循环外统一抛
            except Exception as e:  # noqa: BLE001 —— 单张数据错误上报而非静默跳过
                errors.append(PhotoError(path=photo.path, error=f"{type(e).__name__}: {e}"))
            if on_progress is not None:
                on_progress()  # 每张处理完推进进度（线程安全由回调内部 tick 加锁保证）

        workers = max(1, min(self._concurrency, len(photos))) if photos else 1
        with ThreadPoolExecutor(max_workers=workers) as ex:
            list(ex.map(work, range(len(photos))))

        if unavailable is not None:
            raise BizException(BizCode.MODEL_NOT_READY, f"本地模型不可用：{unavailable}") from unavailable

        scores: list[LocalScore] = [s for s in results if s is not None]  # 保持输入顺序
        n = self._params.compute_n(len(photos))
        m = self._params.compute_m(n)
        survivors = score_converter.to_survivors(self._funnel.apply_funnel(scores, m))
        return AssessResponse(
            group_id=req.group_id, scores=scores, survivors=survivors, n=n, m=m, errors=errors
        )
