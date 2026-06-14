"""层① 本地评分响应。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..enumeration.pk_origin import PkOrigin
from ..vo.local_score import LocalScore
from .common import PhotoError


class SurvivorEntry(BaseModel):
    """通过层① 漏斗、进入层② 的一张候选 + 它为何通过（达标 / 兜底补入）。"""

    path: str
    score: float
    origin: PkOrigin = Field(description="passed=分≥60达标；quota_fill=<60但按保底数补入")


class AssessResponse(BaseModel):
    """层① 评分结果：每张分数明细 + 漏斗收口后的 survivors（进层②候选）。"""

    group_id: str
    scores: list[LocalScore]
    survivors: list[SurvivorEntry] = Field(description="apply_funnel(scores, M) 通过的候选 + 来源")
    n: int = Field(description="基础保底数 N")
    m: int = Field(description="层① 保底数 M = ceil(1.5N)")
    errors: list[PhotoError] = Field(default_factory=list)
