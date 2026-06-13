"""跨模块共享的数据模型。FastAPI 请求/响应与内部流转统一用这些类型。"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Group(BaseModel):
    """一个「瞬间组」：一次拍摄里相似的连拍。"""

    id: str
    photos: list[str] = Field(description="组内照片的本地绝对路径")


class FaceDetail(BaseModel):
    """主脸的人脸信号（供前端透明展示）。无脸时 count=0、其余为 None。"""

    count: int = Field(description="高置信人脸数")
    main_area_ratio: float | None = Field(default=None, description="主脸面积占整图比例")
    main_det_score: float | None = Field(default=None, description="主脸检测置信度")
    main_sharpness: float | None = Field(default=None, description="主脸区拉普拉斯方差（越大越锐）")
    main_eye_ear: float | None = Field(default=None, description="主脸 EAR；None=未知/不可靠")


class Penalty(BaseModel):
    """一条触发的扣分项（中文原因 + 扣的分）。"""

    reason: str
    points: float


class ScoreDetail(BaseModel):
    """层① 单张照片的完整评分明细——所有能给前端看的中间信号都在这。"""

    base: float = Field(description="扣分前的基础分（0–100）")
    tech_quality: float = Field(description="技术质量分 0–1")
    tech_source: str = Field(description="技术质量来源：topiq_nr-face（有脸）或 topiq_nr（无脸）")
    clipiqa: float = Field(description="CLIP-IQA+ 美学分 0–1")
    sharpness: float | None = Field(default=None, description="主体锐度原始值（拉普拉斯方差）")
    sharpness_norm: float = Field(description="主体锐度归一到 0–1")
    entropy: float = Field(description="灰度信息熵 0–8")
    brightness_mean: float
    contrast: float
    underexposed_ratio: float
    overexposed_ratio: float
    face: FaceDetail
    penalties: list[Penalty] = Field(default_factory=list, description="所有触发的扣分项")


class LocalScore(BaseModel):
    """层① 本地模型对单张照片的 0–100 技术质量分 + 可解释理由 + 完整明细。

    评分以技术质量为主（锐度 / 曝光 / 人脸 / IQA 美学）。这一层走 `apply_funnel`
    用保底数 M 筛选，通过的进入层②（大模型）；详见 docs/product-flow.md。
    `detail` 携带全部中间信号，供前端透明展示去留理由。
    """

    path: str
    score: float = Field(ge=0, le=100)
    primary_reason: str = Field(
        default="", description="头条理由（最高优先级的一条，如「脱焦」「闭眼」；全部见 detail.penalties）"
    )
    detail: ScoreDetail | None = Field(default=None, description="完整评分明细")


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


class SurvivorEntry(BaseModel):
    """通过层① 漏斗、进入层② 的一张候选 + 它为何通过（达标 / 兜底补入）。"""

    path: str
    score: float
    origin: PkOrigin = Field(description="passed=分≥60达标；quota_fill=<60但按保底数补入")


class AssessResponse(BaseModel):
    """层① 评分结果：每张分数明细 + 漏斗收口后的 survivors（进层②候选）。"""

    group_id: str
    scores: list[LocalScore]
    survivors: list[SurvivorEntry] = Field(description="apply_funnel(scores, M) 通过的候选 + 来源")
    n: int = Field(description="基础保底数 N")
    m: int = Field(description="层① 保底数 M = ceil(1.5N)")
    errors: list[PhotoError] = Field(default_factory=list)
