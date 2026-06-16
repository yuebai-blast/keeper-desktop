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
from volcenginesdkarkruntime import Ark

from ..config.settings import Settings
from ..enumeration.biz_code import BizCode
from ..exception.errors import BizException
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

    def test_connection(self, req: UpdateSettingsRequest) -> SettingsView:
        """用「待保存的有效值」实调一次极简对话，验证 key+模型+基址能连上。

        不落任何配置——纯连通性校验。失败抛 BizException(SCORER_FAILED) 并带回详情。成功返回当前快照。
        """
        key, model, base_url = self._effective(req)
        client = Ark(api_key=key, base_url=base_url)
        try:
            # max_output_tokens=1 的最小调用：一次性验证鉴权 + 模型 id + 基址是否都有效。
            # 关思考：避免思维链吃掉这 1 token 预算，让连通性校验稳定完成。
            client.responses.create(
                model=model,
                input="ping",
                max_output_tokens=1,
                temperature=0.0,
                thinking={"type": "disabled"},
            )
        except Exception as e:  # noqa: BLE001 —— 任何失败都翻成可读的连接错误回前端
            raise BizException(BizCode.SCORER_FAILED, f"连接失败：{e}") from e
        return self.get()

    def update(self, req: UpdateSettingsRequest) -> SettingsView:
        """先测后存：连接测试不通过则抛错、不落任何配置（「能连上才给保存」）。

        部分更新：仅写入非 None 字段；ark_key 为空白则保持原 key 不动。返回更新后的快照。
        """
        self.test_connection(req)  # 测不通直接上抛，下面的持久化不会执行

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
    def _effective(self, req: UpdateSettingsRequest) -> tuple[str, str, str]:
        """解析「待保存/待测试」的有效三元组：key 留空→用已存 key，model/base_url 留空→用当前值。

        缺 key 或缺 model 直接抛 SCORER_FAILED（连接无从谈起）。
        """
        key = (req.ark_key or "").strip() or self._existing_key()
        if not key:
            raise BizException(BizCode.SCORER_FAILED, "未配置 Ark API Key")
        model = (req.ark_model or "").strip() or self._settings.ark_model
        if not model:
            raise BizException(BizCode.SCORER_FAILED, "未指定模型 id")
        base_url = (req.ark_base_url or "").strip() or self._settings.ark_base_url
        return key, model, base_url

    def _existing_key(self) -> str:
        """已配置的 key（环境变量优先，其次 key 文件）；都没有返回空串。"""
        env = os.environ.get("ARK_API_KEY", "").strip()
        if env:
            return env
        f = self._settings.ark_key_file
        if f.exists():
            return f.read_text(encoding="utf-8").strip()
        return ""

    def _key_present(self) -> bool:
        return bool(self._existing_key())

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
