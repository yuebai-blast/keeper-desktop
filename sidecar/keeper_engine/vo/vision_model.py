"""值对象：火山管理面拉取到的、支持「图片内容理解」的基础模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class VisionModel(BaseModel):
    """一个可用于层②看图打分的候选模型（供设置页下拉选择）。"""

    model_id: str = Field(description="推理调用用的 model id（模型名-主版本）")
    name: str = Field(description="基础模型名称")
    version: str = Field(default="", description="主版本号")
    display_name: str = Field(default="", description="展示名")
