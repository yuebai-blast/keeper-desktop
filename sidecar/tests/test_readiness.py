"""就绪态预热的测试——用桩步骤替代真实模型，验证进度 / 依赖区分 / 重试 / 首次探测。"""

from keeper_engine.config.settings import Settings
from keeper_engine.exception.errors import DependencyMissing
from keeper_engine.service.readiness_service import ReadinessService


class FakeVision:
    """桩 VisionClient：warmup_steps 返回构造时给定的 [(label, fn)]。"""

    def __init__(self, steps):
        self._steps = steps

    def warmup_steps(self):
        return self._steps


def _svc(steps, tmp_path) -> ReadinessService:
    return ReadinessService(FakeVision(steps), Settings(models_dir=tmp_path))


def test_warmup_success_reports_progress(tmp_path):
    svc = _svc([("a", lambda: None), ("b", lambda: None)], tmp_path)
    svc._warmup()
    assert svc.status == "ready"
    assert svc.current == 2 and svc.total == 2 and svc.step == ""


def test_dependency_missing_is_not_retryable(tmp_path):
    def boom():
        raise DependencyMissing("torch 未安装")

    svc = _svc([("a", boom)], tmp_path)
    svc._warmup()
    assert svc.status == "error" and svc.retryable is False
    assert "依赖缺失" in svc.detail


def test_load_failure_is_retryable(tmp_path):
    def boom():
        raise RuntimeError("下载超时")

    svc = _svc([("a", boom)], tmp_path)
    svc._warmup()
    assert svc.status == "error" and svc.retryable is True


def test_retry_only_when_retryable(tmp_path, monkeypatch):
    svc = _svc([("a", lambda: None)], tmp_path)
    monkeypatch.setattr(svc, "start_warmup", lambda: None)  # 不起真线程

    assert svc.retry() is False           # loading 态不可重试
    svc.status, svc.retryable = "error", False
    assert svc.retry() is False           # 依赖缺失的 error 不可重试
    svc.status, svc.retryable = "error", True
    assert svc.retry() is True and svc.status == "loading"


def test_first_run_detection(tmp_path):
    assert _svc([], tmp_path).first_run is True       # 空目录 → 首次
    (tmp_path / "model.onnx").write_bytes(b"x")
    assert _svc([], tmp_path).first_run is False      # 有权重 → 非首次
