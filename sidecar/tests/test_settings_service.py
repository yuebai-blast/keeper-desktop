"""设置页业务（自用版）测试：读 / 测连接 / 先测后存的核心约定。

覆盖：①get 不漏 key 明文 ②测连接缺 key/失败 → SCORER_FAILED ③update 先测后存
（测不通不落配置）④key 写 0600、model 落 config.toml 即时生效、空 key 不覆盖既有。
大模型调用用假 openai.OpenAI 桩掉，不打真网络。
"""

from __future__ import annotations

import tomllib
from types import SimpleNamespace

import pytest

from keeper_engine.config.settings import Settings
from keeper_engine.enumeration.biz_code import BizCode
from keeper_engine.exception.errors import BizException
from keeper_engine.request.settings_request import UpdateSettingsRequest
from keeper_engine.service.settings_service import SettingsService


@pytest.fixture
def svc(tmp_path, monkeypatch):
    monkeypatch.delenv("ARK_API_KEY", raising=False)  # 避免 _existing_key 误判
    settings = Settings(home=tmp_path / "keeper", ark_model="seed-model")
    return SettingsService(settings), settings


def _stub_openai(monkeypatch, *, fail=False):
    """把 openai.OpenAI 换成假实现：fail=True 时 create 抛错，模拟连不上。"""

    def _create(**_kw):
        if fail:
            raise RuntimeError("boom")
        return SimpleNamespace(choices=[])

    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=_create)))
    monkeypatch.setattr("openai.OpenAI", lambda **_kw: fake)


def test_get_reports_key_absent_and_never_leaks_plaintext(svc):
    service, _ = svc
    view = service.get()
    assert view.ark_model == "seed-model"
    assert view.ark_key_set is False
    assert "ark_key" not in view.model_dump()  # 响应结构里压根没有 key 字段


def test_test_connection_missing_key_raises(svc):
    service, _ = svc
    with pytest.raises(BizException) as ei:
        service.test_connection(UpdateSettingsRequest(ark_model="m"))  # 无 key
    assert ei.value.biz is BizCode.SCORER_FAILED


def test_test_connection_wraps_failure(svc, monkeypatch):
    service, _ = svc
    _stub_openai(monkeypatch, fail=True)
    with pytest.raises(BizException) as ei:
        service.test_connection(UpdateSettingsRequest(ark_key="sk", ark_model="m"))
    assert ei.value.biz is BizCode.SCORER_FAILED
    assert "连接失败" in ei.value.msg


def test_test_connection_success_does_not_persist(svc, monkeypatch):
    service, settings = svc
    _stub_openai(monkeypatch)
    view = service.test_connection(UpdateSettingsRequest(ark_key="sk", ark_model="m"))
    assert view.ark_model == "seed-model"  # 测试不落配置
    assert not settings.ark_key_file.exists()  # 测试也不写 key


def test_update_blocked_when_connection_fails(svc, monkeypatch):
    service, settings = svc
    _stub_openai(monkeypatch, fail=True)
    with pytest.raises(BizException):
        service.update(UpdateSettingsRequest(ark_key="sk", ark_model="ep-new"))
    # 测不通：key 没写、model 没改
    assert not settings.ark_key_file.exists()
    assert settings.ark_model == "seed-model"


def test_update_writes_key_0600_after_passing(svc, monkeypatch):
    service, settings = svc
    _stub_openai(monkeypatch)
    view = service.update(UpdateSettingsRequest(ark_key="sk-secret"))
    assert view.ark_key_set is True
    key_file = settings.ark_key_file
    assert key_file.read_text(encoding="utf-8") == "sk-secret"
    assert (key_file.stat().st_mode & 0o777) == 0o600


def test_update_model_takes_effect_in_memory_and_persists_toml(svc, monkeypatch):
    service, settings = svc
    _stub_openai(monkeypatch)
    service.update(UpdateSettingsRequest(ark_key="sk", ark_model="ep-new", ark_base_url="https://x/api"))
    assert settings.ark_model == "ep-new"  # 内存单例即时生效
    assert settings.ark_base_url == "https://x/api"
    data = tomllib.loads((settings.home / "config.toml").read_text(encoding="utf-8"))  # 落库保留
    assert data["ark_model"] == "ep-new"
    assert data["ark_base_url"] == "https://x/api"


def test_blank_key_keeps_existing(svc, monkeypatch):
    service, settings = svc
    _stub_openai(monkeypatch)
    service.update(UpdateSettingsRequest(ark_key="sk-first"))
    # 仅改 model、key 留空 → 用既有 key 通过测试，且不覆盖原 key
    service.update(UpdateSettingsRequest(ark_key="", ark_model="ep-2"))
    assert settings.ark_key_file.read_text(encoding="utf-8") == "sk-first"
    assert settings.ark_model == "ep-2"
