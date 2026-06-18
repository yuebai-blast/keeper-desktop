"""单张照片的去留——最终归档只复制 kept。"""

from __future__ import annotations

from enum import Enum


class Selection(str, Enum):
    """照片去留：初值由层②漏斗给出，用户经 PK / 手动可改。"""

    KEPT = "KEPT"                # 通过（最终会归档）
    DISCARDED = "DISCARDED"      # 未通过
