"""值对象：组装好、送入用户 A/B 擂台的候选。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..enumeration.pk_origin import PkOrigin


class PkEntry(BaseModel):
    """组装好、即将送入用户 A/B 擂台的一张候选。"""

    path: str
    origin: PkOrigin
    score: float = Field(description="层② 大模型分（进 PK 的都来自层② 已打分的候选）")
    reason: str = ""


class PkSet(BaseModel):
    """一个组最终送入擂台的候选集合（len = min(K, max(达标数, N))）。"""

    group_id: str
    entries: list[PkEntry]
