"""值对象：层① 本地评分及其完整明细（供前端透明展示去留理由）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


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


class ScoreComponent(BaseModel):
    """基础分的一个加权构成项：points = value × weight（value 已化为 0–100 制）。"""

    name: str
    value: float = Field(description="信号分（0–100，= 原始 0–1 信号 ×100）")
    weight: float
    points: float = Field(description="对基础分的贡献 = value × weight")


class ScoreDetail(BaseModel):
    """层① 单张照片的完整评分明细——所有能给前端看的中间信号都在这。"""

    base: float = Field(description="扣分前的基础分（0–100）= 各构成项之和")
    base_components: list[ScoreComponent] = Field(default_factory=list, description="基础分的加权构成明细")
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
