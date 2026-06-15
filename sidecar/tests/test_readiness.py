"""就绪态加载编排的测试——用桩 VisionClient 替代真实模型，验证进度/依赖区分/重试/首次探测。"""

from keeper_engine.client.vision_client import MODULE_EXPECTED_MB
from keeper_engine.config.settings import Settings
from keeper_engine.exception.errors import DependencyMissing
from keeper_engine.mapper.model_module_mapper import ModelModuleMapper
from keeper_engine.service.readiness_service import ReadinessService

_KEYS = list(MODULE_EXPECTED_MB)


class FakeVision:
    """桩 VisionClient：load_all 同步逐模块回调；可在指定步抛致命/可重试异常。"""

    def __init__(self, fail: str | None = None, fail_at: int = 0):
        self._fail = fail  # None / "fatal"(DependencyMissing) / "retry"(其它异常)
        self._fail_at = fail_at

    def cleanup_partials(self):
        pass

    def load_all(self, report):
        for i, key in enumerate(_KEYS):
            report(i + 1, len(_KEYS), key, key)
            if self._fail and i == self._fail_at:
                if self._fail == "fatal":
                    raise DependencyMissing("缺少依赖包")
                raise RuntimeError("下载失败")


def _svc(tmp_path, fail=None, fail_at=0) -> ReadinessService:
    settings = Settings(home=tmp_path)
    return ReadinessService(FakeVision(fail, fail_at), settings, ModelModuleMapper(settings))


def test_warmup_success_reports_progress(tmp_path):
    svc = _svc(tmp_path)
    svc._warmup()
    assert svc.status == "ready"
    assert svc.current == len(_KEYS) and svc.total == len(_KEYS) and svc.step == ""
    # 所有模块在 sqlite 标记 ready
    assert all(m.status == "ready" for m in svc._mapper.all())


def test_dependency_missing_is_not_retryable(tmp_path):
    svc = _svc(tmp_path, fail="fatal", fail_at=0)
    svc._warmup()
    assert svc.status == "error" and svc.retryable is False
    assert "依赖缺失" in svc.detail


def test_load_failure_is_retryable(tmp_path):
    svc = _svc(tmp_path, fail="retry", fail_at=2)
    svc._warmup()
    assert svc.status == "error" and svc.retryable is True


def test_snapshot_has_progress_fields(tmp_path):
    svc = _svc(tmp_path)
    snap = svc.snapshot()
    assert set(snap) >= {"status", "detail", "retryable", "first_run", "progress", "modules"}
    assert set(snap["progress"]) == {"current", "total", "step", "downloaded_mb", "speed_mbps", "percent"}


def test_retry_only_when_retryable(tmp_path, monkeypatch):
    svc = _svc(tmp_path)
    monkeypatch.setattr(svc, "start_warmup", lambda: None)  # 不起真线程
    assert svc.retry() is False                # loading 态不可重试
    svc.status, svc.retryable = "error", False
    assert svc.retry() is False                # 依赖缺失的 error 不可重试
    svc.status, svc.retryable = "error", True
    assert svc.retry() is True and svc.status == "loading"


def test_reload_forces_when_not_loading(tmp_path, monkeypatch):
    svc = _svc(tmp_path)
    monkeypatch.setattr(svc, "start_warmup", lambda: None)
    svc.status = "ready"
    assert svc.reload() is True and svc.status == "loading"  # ready 态可强制重载（修复）
    svc.status = "loading"
    assert svc.reload() is False               # 已在加载中则忽略


def test_first_run_detection(tmp_path):
    assert _svc(tmp_path).first_run is True            # 空目录 → 首次
    models = tmp_path / "models"                       # 与 Settings(home).models_dir 一致
    models.mkdir(parents=True, exist_ok=True)
    (models / "model.onnx").write_bytes(b"x")
    assert _svc(tmp_path).first_run is False           # 有权重 → 非首次
