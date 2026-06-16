"""设置页响应：当前大模型配置。

安全约定：**绝不回传 key 明文**——只用 ark_key_set 告诉前端「是否已配置」，
前端据此显示「已配置」占位，留空提交即保持原 key 不变。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SettingsView(BaseModel):
    """当前大模型配置（不含 key 明文）。"""

    ark_model: str = Field(description="Ark 模型 id")
    ark_base_url: str = Field(description="Ark 兼容接口基址")
    ark_concurrency: int = Field(description="打分并发数")
    ark_key_set: bool = Field(description="是否已配置 Ark key（环境变量或 key 文件）")
