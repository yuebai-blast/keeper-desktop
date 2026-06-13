"""「进 PK 规则」的测试——产品最关键的逻辑，对应 docs/product-flow.md。

核心公式：进 PK 数 = min(K, max(达标数, N))，达标 = 分 >= 60。
"""

from keeper_engine.models import PkOrigin, Score
from keeper_engine.ranking import assemble_pk_set


def _scores(*pairs: tuple[str, float]) -> list[Score]:
    return [Score(path=p, score=s, reason="") for p, s in pairs]


def test_all_above_threshold_pass_no_cap():
    """≥60 全部进 PK，不设上限——5 张都过 60 就 5 张全进，按分降序。"""
    scores = _scores(("a", 95), ("b", 88), ("c", 72), ("d", 65), ("e", 61))
    pk = assemble_pk_set("g1", scores, n=3)
    assert [e.path for e in pk.entries] == ["a", "b", "c", "d", "e"]
    assert all(e.origin == PkOrigin.PASSED for e in pk.entries)


def test_quota_fill_when_passed_below_n():
    """≥60 不足 N 时，用 <60 的按分补到 N。"""
    scores = _scores(("a", 90), ("b", 55), ("c", 40), ("d", 20))
    pk = assemble_pk_set("g1", scores, n=3)
    assert len(pk.entries) == 3
    assert pk.entries[0].origin == PkOrigin.PASSED       # a (90)
    assert pk.entries[1].origin == PkOrigin.QUOTA_FILL   # b (55)
    assert pk.entries[2].origin == PkOrigin.QUOTA_FILL   # c (40)


def test_underfull_gives_all_when_k_le_n():
    """巧妇难为无米之炊：幸存 K <= N 时全部进 PK，不报错、不从废片捞。"""
    scores = _scores(("a", 90), ("b", 30))
    pk = assemble_pk_set("g1", scores, n=5)
    assert len(pk.entries) == 2
    assert [e.path for e in pk.entries] == ["a", "b"]
