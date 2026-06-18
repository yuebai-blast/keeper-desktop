"""单张照片的评测状态——驱动重试分支与失败阻塞。"""

from __future__ import annotations

from enum import Enum


class AssessStatus(str, Enum):
    """评测状态：未评测 → 成功 / 层①失败 / 层②失败。与 selection 正交。"""

    NOT_ASSESSED = "NOT_ASSESSED"    # 尚未评测
    SUCCESS = "SUCCESS"              # 评测流程正常走完（不论进没进层②/最终去留）
    LAYER1_FAILED = "LAYER1_FAILED"  # 层①本地评分失败
    LAYER2_FAILED = "LAYER2_FAILED"  # 层②大模型打分失败
