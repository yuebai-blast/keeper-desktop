"""设置页（自用版）业务：读/写大模型配置。

【仅自用版】让用户填自己的 Ark key 直连大模型（LocalDirectScorer）。商业版不装配此 service、
不注册 settings_controller——key 在云端中转，绝不下发客户端（见 .todolist.md 的版本区分方案）。

落地策略（两类配置两套存储，皆即时生效）：
  - key：写 ~/.keeper/ark_key（0600）。scorer 每次调用现读该文件 → 写完立即生效，**绝不入库**。
  - model / base_url：① 更新内存 Settings 单例（项目工作流打分用 settings.ark_model，立即生效）
    ② 落回 ~/.keeper/config.toml（重启后仍保留）。
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

import tomli_w

from ..config.settings import Settings
from ..request.settings_request import UpdateSettingsRequest
from ..response.settings_response import SettingsView


class SettingsService:
    """大模型配置的读写编排（注入 Settings 单例）。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def get(self) -> SettingsView:
        """当前配置快照（不含 key 明文，只报告是否已配置）。"""
        return SettingsView(
            ark_model=self._settings.ark_model,
            ark_base_url=self._settings.ark_base_url,
            ark_concurrency=self._settings.ark_concurrency,
            ark_key_set=self._key_present(),
        )

    def update(self, req: UpdateSettingsRequest) -> SettingsView:
        """部分更新：仅写入非 None 字段；ark_key 为空白则保持原 key 不动。返回更新后的快照。"""
        if req.ark_key is not None and req.ark_key.strip():
            self._write_key(req.ark_key.strip())

        persist: dict[str, str] = {}
        if req.ark_model is not None:
            self._settings.ark_model = req.ark_model.strip()
            persist["ark_model"] = self._settings.ark_model
        if req.ark_base_url is not None and req.ark_base_url.strip():
            self._settings.ark_base_url = req.ark_base_url.strip()
            persist["ark_base_url"] = self._settings.ark_base_url
        if persist:
            self._persist_config(persist)

        return self.get()

    # ── 内部 ────────────────────────────────────────────────────────────
    def _key_present(self) -> bool:
        if os.environ.get("ARK_API_KEY", "").strip():
            return True
        f = self._settings.ark_key_file
        return f.exists() and bool(f.read_text(encoding="utf-8").strip())

    def _write_key(self, key: str) -> None:
        f = self._settings.ark_key_file
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(key, encoding="utf-8")
        os.chmod(f, 0o600)

    def _config_file(self) -> Path:
        # 与 settings 的数据根一致（默认 ~/.keeper/config.toml）；便于测试隔离到临时 home
        return self._settings.home / "config.toml"

    def _persist_config(self, updates: dict[str, str]) -> None:
        path = self._config_file()
        data: dict = {}
        if path.exists():
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        data.update(updates)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as fp:
            tomli_w.dump(data, fp)
