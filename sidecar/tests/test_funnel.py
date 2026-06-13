"""两层通用漏斗 `apply_funnel` 的测试——层①/层② 共用的核心规则。

核心公式：通过数 = min(K, max(达标数, n))，达标 = 分 >= 60。
这里用层① 的 LocalScore 跑，验证规则与具体层无关。详见 docs/product-flow.md。
"""

from keeper_engine.funnel import apply_funnel
from keeper_engine.models import LocalScore


def _scores(*pairs: tuple[str, float]) -> list[LocalScore]:
    return [LocalScore(path=p, score=s) for p, s in pairs]


def test_all_above_threshold_pass_no_cap():
    """≥60 全部通过、不设上限，且都不标兜底；按分降序。"""
    scored = _scores(("a", 95), ("b", 88), ("c", 72), ("d", 65), ("e", 61))
    out = apply_funnel(scored, n=3)
    assert [s.path for s, _ in out] == ["a", "b", "c", "d", "e"]
    assert all(is_fill is False for _, is_fill in out)


def test_quota_fill_when_passed_below_n():
    """达标不足 n 时，用 <60 的按分补到 n，并标记为兜底。"""
    scored = _scores(("a", 90), ("b", 55), ("c", 40), ("d", 20))
    out = apply_funnel(scored, n=3)
    assert [(s.path, is_fill) for s, is_fill in out] == [
        ("a", False),  # 达标
        ("b", True),   # 兜底补入
        ("c", True),   # 兜底补入
    ]


def test_underfull_gives_all_when_k_le_n():
    """巧妇难为无米之炊：输入 K <= n 时全部通过，不报错、不无中生有。"""
    scored = _scores(("a", 90), ("b", 30))
    out = apply_funnel(scored, n=5)
    assert [s.path for s, _ in out] == ["a", "b"]
