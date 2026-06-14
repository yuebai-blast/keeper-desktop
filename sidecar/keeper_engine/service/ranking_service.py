"""层② 出口：把大模型分套漏斗，组装成送入用户 A/B 擂台的候选集。

漏斗规则本身是两层通用的 FunnelService.apply_funnel；这里在它之上加一层 PK 语义：
给每张标注「达标通过 / 兜底补入」的来源（经 score_converter），供前端透明展示去留理由。
对应 docs/product-flow.md：进 PK 数 = min(K, max(达标数, N))，达标 = 大模型分 >= 60。
"""

from __future__ import annotations

from ..converter import score_converter
from ..vo.pk import PkSet
from ..vo.score import Score
from .funnel_service import FunnelService


class RankingService:
    """组装 PK 候选集：漏斗（注入的 FunnelService）+ 来源标注（converter）。"""

    def __init__(self, funnel: FunnelService) -> None:
        self._funnel = funnel

    def assemble_pk_set(self, group_id: str, scores: list[Score], n: int) -> PkSet:
        """把层② 候选的大模型分数 + 漏斗规则组装成送入擂台的候选集。

        scores: 进入层② 的 K 张候选的大模型打分，每张都有分。
        n: 进 PK 下限（基础保底数 N）。

        交给 apply_funnel 决定哪些进 PK（≥60 全进、不足 N 按分补、输入不足时全进），
        再由 converter 翻译成带来源标注的 PkEntry。返回 entries 数 = min(K, max(达标数, N))。
        """
        entries = score_converter.to_pk_entries(self._funnel.apply_funnel(scores, n))
        return PkSet(group_id=group_id, entries=entries)
