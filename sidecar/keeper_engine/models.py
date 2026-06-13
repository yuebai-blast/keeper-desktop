"""跨模块共享的数据模型。FastAPI 请求/响应与内部流转统一用这些类型。"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Group(BaseModel):
    """一个「瞬间组」：一次拍摄里相似的连拍。"""

    id: str
    photos: list[str] = Field(description="组内照片的本地绝对路径")


class LocalScore(BaseModel):
    """层① 本地模型对单张照片的 0–100 技术质量分 + 可解释理由。

    评分以技术质量为主（锐度 / 曝光 / 人脸 / IQA 美学）。这一层走 `apply_funnel`
    用保底数 M 筛选，通过的进入层②（大模型）；详见 docs/product-flow.md。
    """

    path: str
    score: float = Field(ge=0, le=100)
    reason: str = Field(default="", description="中文短理由，如「脱焦」「闭眼」")


class Score(BaseModel):
    """层② 大模型对单张候选的 0–100 审美打分 + 可解释理由。"""

    path: str
    score: float = Field(ge=0, le=100)
    reason: str = Field(default="", description="中文短理由")


class PkOrigin(str, Enum):
    """一张图为何进入 PK——用于前端向用户透明展示去留理由。"""

    PASSED = "passed"          # 大模型分 ≥ 60，达标进入
    QUOTA_FILL = "quota_fill"  # <60 但因数量兜底被补入


class PkEntry(BaseModel):
    """组装好、即将送入用户 A/B 擂台的一张候选。"""

    path: str
    origin: PkOrigin
    score: float = Field(description="层② 大模型分（进 PK 的都来自层② 已打分的候选）")
    reason: str = ""


class PkSet(BaseModel):
    """一个组最终送入擂台的候选集合（len = min(K, max(达标数, N))）。"""

    group_id: str
    entries: list[PkEntry]


# ── /assess 端点（层① 本地评分）的请求/响应 ────────────────────────────────

class PhotoRef(BaseModel):
    """一张待评照片：主路径 + 可选的同名伴随文件（RAW+JPG 双拍）。"""

    path: str
    companions: list[str] = Field(default_factory=list)


class AssessRequest(BaseModel):
    """对一个组做层① 本地评分的请求。"""

    group_id: str
    photos: list[PhotoRef]


class PhotoError(BaseModel):
    """单张照片评分失败（数据问题，如文件损坏）——上报而非静默跳过。"""

    path: str
    error: str


class AssessResponse(BaseModel):
    """层① 评分结果：每张分数 + 漏斗收口后的 survivors（进层②候选）。"""

    group_id: str
    scores: list[LocalScore]
    survivors: list[str] = Field(description="apply_funnel(scores, M) 通过的路径")
    n: int = Field(description="基础保底数 N")
    m: int = Field(description="层① 保底数 M = ceil(1.5N)")
    errors: list[PhotoError] = Field(default_factory=list)
