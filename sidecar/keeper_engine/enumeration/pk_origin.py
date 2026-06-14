"""一张图为何进入 PK / 通过漏斗——用于前端向用户透明展示去留理由。"""

from __future__ import annotations

from enum import Enum


class PkOrigin(str, Enum):
    """一张图为何进入 PK——用于前端向用户透明展示去留理由。"""

    PASSED = "passed"          # 分 ≥ 60，达标进入
    QUOTA_FILL = "quota_fill"  # <60 但因数量兜底被补入
