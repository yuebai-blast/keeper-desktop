"""设置页（自用版）业务：读/写大模型配置。

【仅自用版】让用户填自己的 Ark key 直连大模型（LocalDirectScorer）。商业版不装配此 service、
不注册 settings_controller——key 在云端中转，绝不下发客户端（见 .todolist.md 的版本区分方案）。

落地策略（两类配置两套存储，皆即时生效）：
  - key：写 ~/.keeper/ark_key（0600）。scorer 每次调用现读该文件 → 写完立即生效，**绝不入库**。
  - model / base_url：① 更新内存 Settings 单例（项目工作流打分用 settings.ark_model，立即生效）
    ② 落回 ~/.keeper/config.toml（重启后仍保留）。
  - 火山 AK/SK（仅用于「拉取视觉模型」便利功能，非打分链路）：各写一个 0600 文件、**绝不入库**，
    拉取成功后落盘复用。env（VOLCENGINE_ACCESS_KEY/SECRET_KEY）优先于文件。
"""

from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path

import tomli_w
from volcenginesdkarkruntime import Ark

from ..client.foundation_model_client import FoundationModelClient
from ..config.settings import Settings
from ..enumeration.biz_code import BizCode
from ..exception.errors import BizException
from ..request.settings_request import ListVisionModelsRequest, UpdateSettingsRequest
from ..response.settings_response import SettingsView, VisionModelsView


class SettingsService:
    """大模型配置的读写编排（注入 Settings 单例 + 管理面模型客户端）。"""

    def __init__(self, settings: Settings, foundation_models: FoundationModelClient) -> None:
        self._settings = settings
        self._foundation_models = foundation_models

    def get(self) -> SettingsView:
        """当前配置快照（不含 key / AK / SK 明文，只报告是否已配置）。"""
        return SettingsView(
            ark_model=self._settings.ark_model,
            ark_base_url=self._settings.ark_base_url,
            ark_concurrency=self._settings.ark_concurrency,
            ark_key_set=self._key_present(),
            volc_credentials_set=self._volc_creds_present(),
        )

    def list_vision_models(self, req: ListVisionModelsRequest) -> VisionModelsView:
        """用 AK/SK 调火山管理面拉取支持图片理解的模型；成功后把 AK/SK 落盘复用。

        AK/SK 留空则用已存的（env / 文件）。缺凭据或管理面失败 → FOUNDATION_MODELS_FAILED（带详情）。
        """
        ak, sk = self._effective_volc_creds(req)
        try:
            models = self._foundation_models.list_vision_models(ak, sk)
        except Exception as e:  # noqa: BLE001 —— 任何失败翻成可读的业务错误回前端
            raise BizException(BizCode.FOUNDATION_MODELS_FAILED, f"拉取失败：{e}") from e
        # 能连上才落盘（与「能连上才存 key」一致的先验后存思路）
        if req.volc_ak and req.volc_ak.strip() and req.volc_sk and req.volc_sk.strip():
            self._write_volc_creds(req.volc_ak.strip(), req.volc_sk.strip())
        return VisionModelsView(items=models)

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
        # POSIX 限定权限；Windows 无等价 0600 语义（机密保护依赖用户目录 ACL），跳过避免无效调用。
        if sys.platform != "win32":
            os.chmod(f, 0o600)

    # ── 火山 AK/SK（管理面，拉取视觉模型用）：env 优先，其次各自的 0600 文件 ──────────
    def _existing_volc_creds(self) -> tuple[str, str]:
        """已配置的 AK/SK（env 优先，其次文件）；缺任一返回空串。"""
        ak = os.environ.get("VOLCENGINE_ACCESS_KEY", "").strip()
        sk = os.environ.get("VOLCENGINE_SECRET_KEY", "").strip()
        if not ak and self._settings.volc_ak_file.exists():
            ak = self._settings.volc_ak_file.read_text(encoding="utf-8").strip()
        if not sk and self._settings.volc_sk_file.exists():
            sk = self._settings.volc_sk_file.read_text(encoding="utf-8").strip()
        return ak, sk

    def _volc_creds_present(self) -> bool:
        ak, sk = self._existing_volc_creds()
        return bool(ak and sk)

    def _effective_volc_creds(self, req: ListVisionModelsRequest) -> tuple[str, str]:
        """解析待用 AK/SK：请求留空则回退已存的。缺任一直接抛 FOUNDATION_MODELS_FAILED。"""
        existing_ak, existing_sk = self._existing_volc_creds()
        ak = (req.volc_ak or "").strip() or existing_ak
        sk = (req.volc_sk or "").strip() or existing_sk
        if not ak or not sk:
            raise BizException(BizCode.FOUNDATION_MODELS_FAILED, "未配置火山 AK/SK")
        return ak, sk

    def _write_volc_creds(self, ak: str, sk: str) -> None:
        for f, val in ((self._settings.volc_ak_file, ak), (self._settings.volc_sk_file, sk)):
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(val, encoding="utf-8")
            # POSIX 限定权限；Windows 无等价 0600 语义（机密保护依赖用户目录 ACL），跳过避免无效调用。
            if sys.platform != "win32":
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
