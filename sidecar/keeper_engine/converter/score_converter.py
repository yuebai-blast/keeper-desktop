"""把漏斗结果（带「达标 / 兜底补入」标记）翻译成带 origin 的对外条目。

漏斗规则本身两层通用（见 service/funnel_service.py），这里只负责把结果翻成前端能透明展示
去留理由的条目：层① → SurvivorEntry，层② → PkEntry。
"""

from __future__ import annotations

from typing import Sequence

from ..enumeration.pk_origin import PkOrigin
from ..response.assess_response import SurvivorEntry
from ..vo.local_score import LocalScore
from ..vo.pk import PkEntry
from ..vo.score import Score


def to_survivors(funnel_result: Sequence[tuple[LocalScore, bool]]) -> list[SurvivorEntry]:
    """层① 漏斗结果 → survivors（进层② 候选）。is_quota_fill=True 标记兜底补入（<60）。"""
    return [
        SurvivorEntry(
            path=s.path, score=s.score,
            origin=PkOrigin.QUOTA_FILL if is_quota_fill else PkOrigin.PASSED,
        )
        for s, is_quota_fill in funnel_result
    ]


def to_pk_entries(funnel_result: Sequence[tuple[Score, bool]]) -> list[PkEntry]:
    """层② 漏斗结果 → 送入擂台的 PK 候选。is_quota_fill=True 标记兜底补入（<60）。"""
    return [
        PkEntry(
            path=s.path,
            origin=PkOrigin.QUOTA_FILL if is_quota_fill else PkOrigin.PASSED,
            score=s.score, reason=s.reason,
        )
        for s, is_quota_fill in funnel_result
    ]
