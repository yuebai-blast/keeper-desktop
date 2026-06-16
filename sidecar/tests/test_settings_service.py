"""设置页业务（自用版）测试：读写大模型配置的核心约定。

覆盖：①key 写 0600 文件且不回传明文 ②model/base_url 即时更新内存单例 + 落 config.toml
③部分更新（空 ark_key 不动既有 key）。
"""

from __future__ import annotations

import tomllib

import pytest

from keeper_engine.config.settings import Settings
from keeper_engine.request.settings_request import UpdateSettingsRequest
from keeper_engine.service.settings_service import SettingsService


@pytest.fixture
def svc(tmp_path, monkeypatch):
    # 清掉可能存在的环境变量，避免 _key_present 误判
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    settings = Settings(home=tmp_path / "keeper", ark_model="seed-model")
    return SettingsService(settings), settings


def test_get_reports_key_absent_and_never_leaks_plaintext(svc):
    service, _ = svc
    view = service.get()
    assert view.ark_model == "seed-model"
    assert view.ark_key_set is False
    # 响应模型里压根没有 key 字段——结构上保证不回传明文
    assert "ark_key" not in view.model_dump()


def test_update_writes_key_0600_and_marks_present(svc):
    service, settings = svc
    view = service.update(UpdateSettingsRequest(ark_key="sk-secret"))
    assert view.ark_key_set is True
    key_file = settings.ark_key_file
    assert key_file.read_text(encoding="utf-8") == "sk-secret"
    assert (key_file.stat().st_mode & 0o777) == 0o600


def test_update_model_takes_effect_in_memory_and_persists_toml(svc):
    service, settings = svc
    service.update(UpdateSettingsRequest(ark_model="ep-new", ark_base_url="https://x/api"))
    # ① 内存单例即时生效（项目工作流打分读 settings.ark_model）
    assert settings.ark_model == "ep-new"
    assert settings.ark_base_url == "https://x/api"
    # ② 落回 config.toml（重启后保留）
    data = tomllib.loads((settings.home / "config.toml").read_text(encoding="utf-8"))
    assert data["ark_model"] == "ep-new"
    assert data["ark_base_url"] == "https://x/api"


def test_blank_key_keeps_existing(svc):
    service, settings = svc
    service.update(UpdateSettingsRequest(ark_key="sk-first"))
    # 仅改 model、key 留空 → 不动既有 key
    service.update(UpdateSettingsRequest(ark_key="", ark_model="ep-2"))
    assert settings.ark_key_file.read_text(encoding="utf-8") == "sk-first"
    assert settings.ark_model == "ep-2"
