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


class ListVisionModelsRequest(BaseModel):
    """拉取「支持图片理解」的模型列表（自用版便利功能）。

    AK/SK 为火山「管理面」凭据，与打分用的 ARK_API_KEY 是两套：仅用于查模型列表，全程可选。
    留空则用已存的 AK/SK（env 或 ~/.keeper 文件）；拉取成功后会把本次传入的 AK/SK 落盘复用。
    """

    volc_ak: str | None = Field(default=None, description="火山 Access Key；空/缺省=用已存的")
    volc_sk: str | None = Field(default=None, description="火山 Secret Key；空/缺省=用已存的")
