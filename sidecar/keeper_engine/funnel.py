"""两层级联漏斗的通用规则——整个产品最关键的逻辑。

本地层（层①）与在线 LLM 层（层②）的筛选规则完全一样，只是传入的保底数不同
（层① 为 M、层② 为 N），所以抽象成一个可复用的 `apply_funnel(scores, n)`。
详见 docs/product-flow.md。

一句话：60 分是「资格线」（达标就过、多少张都过），保底数是「饥荒线」
（达标太少时按分补够），输入不够时就全放行。
"""

from __future__ import annotations

from typing import Protocol, Sequence, TypeVar


class _Scored(Protocol):
    """凡是带 0–100 分的对象都能过漏斗（层① 的 LocalScore、层② 的 Score）。"""

    path: str
    score: float


T = TypeVar("T", bound=_Scored)

# 「资格线」：分 ≥ 此值的候选无条件全部通过，不设上限。两层各自校准，默认都是 60。
SCORE_THRESHOLD = 60.0


def apply_funnel(scored: Sequence[T], n: int) -> list[tuple[T, bool]]:
    """对一层的打分结果套用漏斗规则，决定哪些通过到下一层。

    scored: 这一层输入的 K 张打分对象（每张都有 0–100 的 `score`）。
    n: 该层保底数（层① 传 M、层② 传 N）。

    规则（详见 docs/product-flow.md）：
      ① 质量主规则：分 ≥ 60 的全部通过，不设上限。
      ② 数量兜底：达标不足保底数时，用 <60 的按分从高到低补。
      ③ 巧妇难为无米之炊：通过数不超过输入数 K；K <= n 时 K 张全过。

    返回按分降序的 [(item, is_quota_fill)]，长度 = min(K, max(达标数, n))；
    is_quota_fill 标记该张是「兜底补入」（<60）还是「达标通过」（≥60）。
    """
    desc = sorted(scored, key=lambda s: s.score, reverse=True)
    passed = sum(1 for s in desc if s.score >= SCORE_THRESHOLD)
    target = max(passed, n)  # 想要的张数：达标的全要，至少 n 张
    # 切片天然实现 min(K, target)——输入不够就少给，绝不从无到有捞。
    return [(s, s.score < SCORE_THRESHOLD) for s in desc[:target]]
