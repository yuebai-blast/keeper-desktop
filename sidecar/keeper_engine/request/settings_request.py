"""设置页（自用版）更新请求：配置大模型 key / 模型 id / 基址。

仅自用版需要——让用户填自己的 Ark key 直连大模型（LocalDirectScorer）。
商业版不暴露此入口（key 在云端中转，不下发客户端）。
所有字段可选：只更新传入的字段；ark_key 为空字符串/缺省时不改动既有 key。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class UpdateSettingsRequest(BaseModel):
    """更新大模型配置（部分更新，None 表示该字段不动）。"""

    ark_key: str | None = Field(default=None, description="Ark API key 明文；写入 ~/.keeper/ark_key（0600）。空/缺省=不改")
    ark_model: str | None = Field(default=None, description="Ark 模型 id（接入点/模型名）")
    ark_base_url: str | None = Field(default=None, description="Ark 兼容接口基址")
