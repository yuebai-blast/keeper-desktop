"""层② 大模型打分响应。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..vo.pk import PkEntry
from ..vo.score import Score
from .common import PhotoError


class ScoreResponse(BaseModel):
    """层② 打分结果：每张分数 + 漏斗收口组装的 PK 候选集。"""

    group_id: str
    scores: list[Score]
    pk: list[PkEntry] = Field(description="进 PK 的候选（assemble_pk_set 结果，含 passed/quota_fill 来源）")
    n: int = Field(description="基础保底数 N")
    errors: list[PhotoError] = Field(default_factory=list)
