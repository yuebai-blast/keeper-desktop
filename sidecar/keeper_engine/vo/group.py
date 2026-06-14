"""值对象：一个「瞬间组」。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Group(BaseModel):
    """一个「瞬间组」：一次拍摄里相似的连拍。"""

    id: str
    photos: list[str] = Field(description="组内照片的本地绝对路径")
