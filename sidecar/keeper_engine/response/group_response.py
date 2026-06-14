"""分组响应。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..vo.group import Group
from .common import PhotoError


class GroupResponse(BaseModel):
    """分组结果：若干瞬间组 + 读取失败的照片。"""

    groups: list[Group]
    errors: list[PhotoError] = Field(default_factory=list)
