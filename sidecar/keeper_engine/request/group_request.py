"""分组请求。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class GroupRequest(BaseModel):
    """对一批照片做分组的请求。"""

    photos: list[str] = Field(description="照片本地绝对路径")
