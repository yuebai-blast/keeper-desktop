"""设置页业务（自用版）测试：读 / 测连接 / 先测后存的核心约定。

覆盖：①get 不漏 key 明文 ②测连接缺 key/失败 → SCORER_FAILED ③update 先测后存
（测不通不落配置）④key 写 0600、model 落 config.toml 即时生效、空 key 不覆盖既有。
大模型调用用假 Ark 客户端桩掉，不打真网络。
"""

from __future__ import annotations

import tomllib
from types import SimpleNamespace

import pytest

from keeper_engine.config.settings import Settings
from keeper_engine.enumeration.biz_code import BizCode
from keeper_engine.exception.errors import BizException
from keeper_engine.request.settings_request import ListVisionModelsRequest, UpdateSettingsRequest
from keeper_engine.service.settings_service import SettingsService
from keeper_engine.vo.vision_model import VisionModel


class _FakeFoundationModels:
    """桩管理面客户端：记录收到的 AK/SK；fail=True 时抛错模拟管理面失败。"""

    def __init__(self, *, fail=False):
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    def list_vision_models(self, ak, sk):
        self.calls.append((ak, sk))
        if self.fail:
            raise RuntimeError("mgmt boom")
        return [VisionModel(model_id="doubao-seed-2-0-pro-260215", name="doubao-seed-2-0-pro",
                            version="260215", display_name="Doubao Seed 2.0 Pro")]


@pytest.fixture
def svc(tmp_path, monkeypatch):
    monkeypatch.delenv("ARK_API_KEY", raising=False)  # 避免 _existing_key 误判
    monkeypatch.delenv("VOLCENGINE_ACCESS_KEY", raising=False)  # 避免 _existing_volc_creds 误判
    monkeypatch.delenv("VOLCENGINE_SECRET_KEY", raising=False)
    settings = Settings(home=tmp_path / "keeper", ark_model="seed-model")
    fm = _FakeFoundationModels()
    return SettingsService(settings, fm), settings, fm


def _stub_ark(monkeypatch, *, fail=False):
    """把 settings_service 里引用的 Ark 换成假实现：fail=True 时 create 抛错，模拟连不上。"""

    def _create(**_kw):
        if fail:
            raise RuntimeError("boom")
        return SimpleNamespace(output=[])

    fake = SimpleNamespace(responses=SimpleNamespace(create=_create))
    monkeypatch.setattr("keeper_engine.service.settings_service.Ark", lambda **_kw: fake)


def test_get_reports_key_absent_and_never_leaks_plaintext(svc):
    service, _, _ = svc
    view = service.get()
    assert view.ark_model == "seed-model"
    assert view.ark_key_set is False
    assert "ark_key" not in view.model_dump()  # 响应结构里压根没有 key 字段


def test_test_connection_missing_key_raises(svc):
    service, _, _ = svc
    with pytest.raises(BizException) as ei:
        service.test_connection(UpdateSettingsRequest(ark_model="m"))  # 无 key
    assert ei.value.biz is BizCode.SCORER_FAILED


def test_test_connection_wraps_failure(svc, monkeypatch):
    service, _, _ = svc
    _stub_ark(monkeypatch, fail=True)
    with pytest.raises(BizException) as ei:
        service.test_connection(UpdateSettingsRequest(ark_key="sk", ark_model="m"))
    assert ei.value.biz is BizCode.SCORER_FAILED
    assert "连接失败" in ei.value.msg


def test_test_connection_success_does_not_persist(svc, monkeypatch):
    service, settings, _ = svc
    _stub_ark(monkeypatch)
    view = service.test_connection(UpdateSettingsRequest(ark_key="sk", ark_model="m"))
    assert view.ark_model == "seed-model"  # 测试不落配置
    assert not settings.ark_key_file.exists()  # 测试也不写 key


def test_update_blocked_when_connection_fails(svc, monkeypatch):
    service, settings, _ = svc
    _stub_ark(monkeypatch, fail=True)
    with pytest.raises(BizException):
        service.update(UpdateSettingsRequest(ark_key="sk", ark_model="ep-new"))
    # 测不通：key 没写、model 没改
    assert not settings.ark_key_file.exists()
    assert settings.ark_model == "seed-model"


def test_update_writes_key_0600_after_passing(svc, monkeypatch):
    service, settings, _ = svc
    _stub_ark(monkeypatch)
    view = service.update(UpdateSettingsRequest(ark_key="sk-secret"))
    assert view.ark_key_set is True
    key_file = settings.ark_key_file
    assert key_file.read_text(encoding="utf-8") == "sk-secret"
    assert (key_file.stat().st_mode & 0o777) == 0o600


def test_update_model_takes_effect_in_memory_and_persists_toml(svc, monkeypatch):
    service, settings, _ = svc
    _stub_ark(monkeypatch)
    service.update(UpdateSettingsRequest(ark_key="sk", ark_model="ep-new", ark_base_url="https://x/api"))
    assert settings.ark_model == "ep-new"  # 内存单例即时生效
    assert settings.ark_base_url == "https://x/api"
    data = tomllib.loads((settings.home / "config.toml").read_text(encoding="utf-8"))  # 落库保留
    assert data["ark_model"] == "ep-new"
    assert data["ark_base_url"] == "https://x/api"


def test_blank_key_keeps_existing(svc, monkeypatch):
    service, settings, _ = svc
    _stub_ark(monkeypatch)
    service.update(UpdateSettingsRequest(ark_key="sk-first"))
    # 仅改 model、key 留空 → 用既有 key 通过测试，且不覆盖原 key
    service.update(UpdateSettingsRequest(ark_key="", ark_model="ep-2"))
    assert settings.ark_key_file.read_text(encoding="utf-8") == "sk-first"
    assert settings.ark_model == "ep-2"


# ── 拉取视觉模型（AK/SK 管理面）─────────────────────────────────────────────
def test_list_vision_models_missing_creds_raises(svc):
    service, _, fm = svc
    with pytest.raises(BizException) as ei:
        service.list_vision_models(ListVisionModelsRequest())  # 无 AK/SK、env 也无
    assert ei.value.biz is BizCode.FOUNDATION_MODELS_FAILED
    assert fm.calls == []  # 缺凭据时根本不该调管理面


def test_list_vision_models_wraps_management_failure(tmp_path, monkeypatch):
    monkeypatch.delenv("VOLCENGINE_ACCESS_KEY", raising=False)
    monkeypatch.delenv("VOLCENGINE_SECRET_KEY", raising=False)
    settings = Settings(home=tmp_path / "keeper")
    fm = _FakeFoundationModels(fail=True)
    service = SettingsService(settings, fm)
    with pytest.raises(BizException) as ei:
        service.list_vision_models(ListVisionModelsRequest(volc_ak="ak", volc_sk="sk"))
    assert ei.value.biz is BizCode.FOUNDATION_MODELS_FAILED
    assert "拉取失败" in ei.value.msg
    assert not settings.volc_ak_file.exists()  # 失败不落盘


def test_list_vision_models_success_persists_creds_0600(svc):
    service, settings, fm = svc
    view = service.list_vision_models(ListVisionModelsRequest(volc_ak="my-ak", volc_sk="my-sk"))
    assert [m.model_id for m in view.items] == ["doubao-seed-2-0-pro-260215"]
    assert fm.calls == [("my-ak", "my-sk")]  # AK/SK 透传给管理面客户端
    # 成功后落盘复用，且 0600
    assert settings.volc_ak_file.read_text(encoding="utf-8") == "my-ak"
    assert settings.volc_sk_file.read_text(encoding="utf-8") == "my-sk"
    assert (settings.volc_ak_file.stat().st_mode & 0o777) == 0o600
    assert (settings.volc_sk_file.stat().st_mode & 0o777) == 0o600


def test_list_vision_models_uses_stored_creds_when_blank(svc):
    service, settings, fm = svc
    # 先存一次
    service.list_vision_models(ListVisionModelsRequest(volc_ak="stored-ak", volc_sk="stored-sk"))
    # 再次留空 → 回退已存的 AK/SK
    service.list_vision_models(ListVisionModelsRequest())
    assert fm.calls[-1] == ("stored-ak", "stored-sk")
    assert service.get().volc_credentials_set is True


# ── Windows 兼容：机密文件写盘跳过 POSIX chmod ──────────────────────────────
def test_secret_write_skips_chmod_on_windows(svc, monkeypatch):
    """Windows 上 POSIX 0600 无意义：不应调用 os.chmod（避免无效/异常），仍正常写文件。"""
    import sys
    from unittest.mock import patch

    service, settings, _ = svc
    _stub_ark(monkeypatch)  # 桩掉 update 里的连接测试，避免打真网络

    with patch.object(sys, "platform", "win32"), patch("os.chmod") as chmod:
        service.update(UpdateSettingsRequest(ark_key="sk-test-123"))  # 写 ark key → _write_key
        chmod.assert_not_called()

    assert settings.ark_key_file.read_text(encoding="utf-8").strip() == "sk-test-123"
