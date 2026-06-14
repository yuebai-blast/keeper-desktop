"""层② 大模型打分请求。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ScoreRequest(BaseModel):
    """对一个组的层① survivors 做层② 大模型打分的请求。"""

    group_id: str
    photos: list[str] = Field(description="层① 通过的候选原图路径（服务端生成低清预览后上传）")
    group_total: int = Field(description="该组原始照片总数，用于算基础保底数 N")
    model: str | None = Field(default=None, description="Ark 模型 id；不填用服务端默认/环境变量")
