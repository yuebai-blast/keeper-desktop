"""值对象：层② 大模型对单张候选的打分结果。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Score(BaseModel):
    """层② 大模型对单张候选的 0–100 审美打分 + 可解释理由 + 具体瑕疵。"""

    path: str
    score: float = Field(ge=0, le=100)
    reason: str = Field(default="", description="中文短理由（打这个分的主要依据）")
    flaws: str = Field(default="", description="模型列出的具体瑕疵，逗号分隔；无则空")
