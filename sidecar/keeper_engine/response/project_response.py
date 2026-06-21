"""项目工作流响应体。

视图模型与存储实体解耦：用 pydantic from_attributes 从实体投影，避免直接暴露 SQLModel table。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from ..vo.local_score import ScoreDetail
from .common import PhotoError


class ProjectPreviewResponse(BaseModel):
    """源文件夹预览：数量、拍摄时间范围、拍摄地（尽力而为，可空）。"""

    count: int
    time_start: datetime | None = None
    time_end: datetime | None = None
    location: str | None = None
    errors: list[PhotoError] = Field(default_factory=list)


class ProjectView(BaseModel):
    """对外的项目视图。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    source_folder: str
    workspace_dir: str
    target_dir: str
    status: str
    photo_count: int
    time_start: datetime | None = None
    time_end: datetime | None = None
    location: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class GroupSummary(BaseModel):
    """分组列表里的一组摘要（含计数）。"""

    group_key: str
    location: str | None = None
    time_start: datetime | None = None
    time_end: datetime | None = None
    status: str
    photo_count: int
    kept_count: int
    failed_count: int = 0  # 评测失败且未忽略的张数（>0 时本组裁决被锁）
    photo_paths: list[str] = Field(default_factory=list)  # 组内照片的 workspace 路径（供列表页缩略图预览）
    photo_names: list[str] = Field(default_factory=list)  # 与 photo_paths 平行：原始相对路径（带原文件名，供展示）


class PhotoView(BaseModel):
    """组详情/PK 里的一张照片完整信息（层①必有，层②有则展示）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    workspace_path: str
    original_path: str
    filename: str
    capture_time: datetime | None = None
    location: str | None = None
    group_key: str | None = None
    local_score: float | None = None
    local_detail: ScoreDetail | None = None
    llm_score: float | None = None
    llm_reason: str = ""
    llm_flaws: str = ""
    llm_editable: str = ""
    llm_edit_advice: str = ""
    llm_is_junk: bool = False
    origin: str | None = None
    selection: str | None = None
    rescued: bool = False
    assess_status: str = "NOT_ASSESSED"   # 评测状态（见 AssessStatus）
    assess_error: str | None = None        # 层①/层②评测失败原因（null=正常）
    assess_error_ignored: bool = False     # 用户是否忽略该失败


class PkView(BaseModel):
    """PK 进度视图。current 为当前一对的 workspace 路径（前端映射回照片卡片）。"""

    current: list[str] | None = None
    pool_remaining: int = 0
    kept_aside: list[str] = Field(default_factory=list)
    done: bool = False
    can_undo: bool = False


class ProjectDetailResponse(BaseModel):
    """项目详情：项目 + 各组摘要。"""

    project: ProjectView
    groups: list[GroupSummary]


class GroupDetailResponse(BaseModel):
    """组详情：组摘要 + 全部照片 + PK 进度（若有）。"""

    project_id: int
    group: GroupSummary
    photos: list[PhotoView]
    pk: PkView | None = None
    errors: list[PhotoError] = Field(default_factory=list)


class CompleteResponse(BaseModel):
    """完成阶段结果。"""

    output_dir: str
    kept_count: int


class AssessProgress(BaseModel):
    """评测实时进度（内存侧信道，非持久化）。

    组级（group_index/group_count）+ 照片级（phase/done/total）两层：
    一键通过两层都用，单组评测只用照片级（组级恒为 1/1）。
    """

    phase: str            # 见 AssessPhase（IDLE/LAYER1/LAYER2/DONE）
    done: int             # 当前阶段已处理张数
    total: int            # 当前阶段总张数
    group_index: int      # 当前第几组（1-based）；空闲为 0
    group_count: int      # 本轮总组数；空闲为 0
    group_key: str | None  # 当前正在评测的组 key（空闲为 None）
