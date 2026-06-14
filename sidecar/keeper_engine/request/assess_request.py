"""层① 本地评分请求。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PhotoRef(BaseModel):
    """一张待评照片：主路径 + 可选的同名伴随文件（RAW+JPG 双拍）。"""

    path: str
    companions: list[str] = Field(default_factory=list)


class AssessRequest(BaseModel):
    """对一个组做层① 本地评分的请求。"""

    group_id: str
    photos: list[PhotoRef]
