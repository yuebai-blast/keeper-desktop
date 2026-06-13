"""保底数 N / M 计算的测试——对应 product-flow.md「N 怎么定」。"""

from keeper_engine.params import compute_m, compute_n


def test_compute_n_takes_max_of_pct_and_fixed():
    assert compute_n(10) == 3        # max(ceil(10*0.2)=2, 3) = 3，小组靠固定值兜底
    assert compute_n(100) == 20      # max(ceil(100*0.2)=20, 3) = 20，大组随百分比放大
    assert compute_n(0) == 3         # 空组退化为固定值
    assert compute_n(40, pct=0.25, fixed=5) == 10


def test_compute_m_is_one_and_half_n_ceil():
    assert compute_m(3) == 5         # ceil(4.5)
    assert compute_m(20) == 30
    assert compute_m(2) == 3         # ceil(3.0)
