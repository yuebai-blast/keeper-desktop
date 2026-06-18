"""一次 PK 对决的四种结局——见 PkService 状态机。"""

from __future__ import annotations

from enum import Enum


class PkOutcome(str, Enum):
    """用户在擂台上对当前一对照片的选择。"""

    PICK_LEFT = "PICK_LEFT"    # 选左：左留下继续守擂，右淘汰
    PICK_RIGHT = "PICK_RIGHT"  # 选右：右留下继续守擂，左淘汰
    KEEP_BOTH = "KEEP_BOTH"    # 都选：两张都通过、不再参与，下对取两张新图
    DROP_BOTH = "DROP_BOTH"    # 都不选：两张都淘汰，下对取两张新图
