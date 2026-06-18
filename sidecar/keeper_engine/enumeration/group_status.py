"""瞬间组的处理状态——完成门禁要求全部组 confirmed。"""

from __future__ import annotations

from enum import Enum


class GroupStatus(str, Enum):
    """组状态机：未评测 → 已评测待用户 → 用户已确认。"""

    PENDING = "PENDING"          # 尚未跑层①/层②评测
    ASSESSED = "ASSESSED"        # 已评测，等用户处理（PK/确认）
    CONFIRMED = "CONFIRMED"      # 用户已确认（标识，可反复改回）
