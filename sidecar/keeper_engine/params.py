"""保底数计算——对应 docs/product-flow.md「N 怎么定」。

N（基础保底数，也是层② 保底数）= max(ceil(组照片总数 × 百分比), 固定值)  # 取大，不设上限
M（层① 本地保底数）            = ceil(1.5 × N)                          # 比 N 放宽 50%

百分比与固定值是可调旋钮（默认 20% 与 3）。取大而非 clamp：小组靠固定值兜底，大组随百分比放大。
"""

from __future__ import annotations

import math

DEFAULT_PCT = 0.2
DEFAULT_FIXED = 3


def compute_n(total: int, pct: float = DEFAULT_PCT, fixed: int = DEFAULT_FIXED) -> int:
    """层② 基础保底数 N = max(ceil(total × pct), fixed)。total<=0 时退化为 fixed。"""
    if total <= 0:
        return fixed
    return max(math.ceil(total * pct), fixed)


def compute_m(n: int) -> int:
    """层① 本地保底数 M = ceil(1.5 × N)。"""
    return math.ceil(1.5 * n)
