"""层① 并发编排测试——用桩 Prescreen/Readiness 验证并发下的保序与容错，不加载真实模型。"""

import threading
import time

import pytest

from keeper_engine.enumeration.biz_code import BizCode
from keeper_engine.exception.errors import BizException, VisionUnavailable
from keeper_engine.request.assess_request import AssessRequest, PhotoRef
from keeper_engine.service.assess_service import AssessService
from keeper_engine.service.funnel_service import FunnelService
from keeper_engine.service.params_service import ParamsService
from keeper_engine.vo.local_score import LocalScore


class FakeReadiness:
    def __init__(self, status="ready", detail=""):
        self.status = status
        self.detail = detail


class FakePrescreen:
    """按路径名末位数字给分；可注入 sleep 强制线程交错，记录最大并发数。"""

    def __init__(self, sleep=0.0, fail_paths=(), unavailable_paths=()):
        self._sleep = sleep
        self._fail = set(fail_paths)
        self._unavailable = set(unavailable_paths)
        self._active = 0
        self._max_active = 0
        self._lock = threading.Lock()

    def assess_photo(self, path, companions=()):
        with self._lock:
            self._active += 1
            self._max_active = max(self._max_active, self._active)
        try:
            if self._sleep:
                time.sleep(self._sleep)
            if path in self._unavailable:
                raise VisionUnavailable("model gone")
            if path in self._fail:
                raise ValueError("broken file")
            score = float(int(path[-1]) * 10)  # img0→0 … img9→90
            return LocalScore(path=path, score=score, detail=None)
        finally:
            with self._lock:
                self._active -= 1


def _svc(prescreen, readiness=None, concurrency=4):
    return AssessService(
        prescreen=prescreen,
        readiness=readiness or FakeReadiness(),
        funnel=FunnelService(),
        params=ParamsService(),
        concurrency=concurrency,
    )


def _req(n):
    return AssessRequest(group_id="g", photos=[PhotoRef(path=f"img{i}") for i in range(n)])


def test_results_keep_input_order_under_concurrency():
    pre = FakePrescreen(sleep=0.02)
    resp = _svc(pre, concurrency=4).assess(_req(6))
    assert [s.path for s in resp.scores] == [f"img{i}" for i in range(6)]
    assert pre._max_active > 1  # 确实并发了


def test_single_bad_photo_recorded_in_errors_not_fatal():
    resp = _svc(FakePrescreen(fail_paths={"img2"})).assess(_req(4))
    assert {e.path for e in resp.errors} == {"img2"}
    assert {s.path for s in resp.scores} == {"img0", "img1", "img3"}


def test_vision_unavailable_raises_model_not_ready():
    with pytest.raises(BizException) as ei:
        _svc(FakePrescreen(unavailable_paths={"img1"})).assess(_req(3))
    assert ei.value.biz == BizCode.MODEL_NOT_READY


def test_not_ready_blocks():
    with pytest.raises(BizException) as ei:
        _svc(FakePrescreen(), readiness=FakeReadiness(status="loading")).assess(_req(2))
    assert ei.value.biz == BizCode.MODEL_NOT_READY


def test_on_progress_called_once_per_photo():
    ticks = []
    _svc(FakePrescreen()).assess(_req(5), on_progress=lambda: ticks.append(1))
    assert len(ticks) == 5


def test_on_progress_counts_failed_photos_too():
    ticks = []
    _svc(FakePrescreen(fail_paths={"img2"})).assess(_req(4), on_progress=lambda: ticks.append(1))
    assert len(ticks) == 4  # 失败图也算「已处理」，照常推进进度
