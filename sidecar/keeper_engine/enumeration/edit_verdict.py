"""层② 修图判定：能不能修 / 值不值得修——用于前端给用户后期处置建议。"""

from __future__ import annotations

from enum import Enum


class EditVerdict(str, Enum):
    """一张照片的修图判定四态。"""

    READY = "READY"                  # 开图即用：骨架好且无明显可修项
    WORTH_EDITING = "WORTH_EDITING"  # 值得修：有可修的皮肤瑕疵且修了能提升
    NOT_WORTH = "NOT_WORTH"          # 能修但提升有限、不划算
    UNFIXABLE = "UNFIXABLE"          # 压根修不了：骨架硬伤后期救不回

    @classmethod
    def coerce(cls, value: str | None) -> str:
        """把模型输出的字符串落到合法枚举值；非法/缺失兜底为 READY（安全默认，不静默吞错只是给保底）。"""
        v = (value or "").strip()
        return v if v in cls._value2member_map_ else cls.READY.value
