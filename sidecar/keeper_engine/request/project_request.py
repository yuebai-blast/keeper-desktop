"""项目工作流请求体。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..enumeration.pk_outcome import PkOutcome
from ..enumeration.selection import Selection


class ProjectPreviewRequest(BaseModel):
    """预览源文件夹：统计数量、拍摄时间范围、拍摄地（不建项目）。"""

    folder: str = Field(description="用户选中的源文件夹绝对路径")


class ProjectCreateRequest(BaseModel):
    """新建项目：校验名唯一 → 复制副本到 workspace。"""

    name: str = Field(description="项目名（唯一，作为 workspace/输出子目录名）")
    source_folder: str = Field(description="源文件夹绝对路径")
    guarantee_pct: int | None = Field(
        default=None, description="保底百分比（整数 1–100，如 20 表示 20%）；缺省=用默认 20"
    )
    guarantee_fixed: int | None = Field(
        default=None, description="保底固定值（整数 >=1）；缺省=用默认 3"
    )


class SelectionChange(BaseModel):
    """一张照片的去留/救回改动。selection/rescued 为 None 表示该项不变。"""

    photo_id: int
    selection: Selection | None = None
    rescued: bool | None = None


class SelectionUpdateRequest(BaseModel):
    """批量更新组内照片的去留与救回标记。"""

    changes: list[SelectionChange]


class PkStartRequest(BaseModel):
    """开始/恢复 PK。pool 为参与对决的照片 workspace 路径（通常=通过∪救回）。"""

    pool: list[str] = Field(default_factory=list)
    restart: bool = Field(default=False, description="True=丢弃已有进度重开；False=有进度则恢复")


class PkChooseRequest(BaseModel):
    """对当前一对照片的一次选择。"""

    outcome: PkOutcome


class ReviewSelectionRequest(BaseModel):
    """二次预览页批量改去留：把一批照片整体置为 KEPT 或 DISCARDED。"""

    photo_ids: list[int]
    selection: Selection


class RetryRequest(BaseModel):
    """重试评测失败图。photo_id 为 None=该组全部未解决失败图；否则只重试该张。"""

    photo_id: int | None = None


class IgnoreFailuresRequest(BaseModel):
    """忽略评测失败（解除对本组裁决的阻塞）。photo_id 为 None=全部失败图。"""

    photo_id: int | None = None


class MovePhotoRequest(BaseModel):
    """把一张照片移到目标组（只改归属，保留全部明细）。"""

    target_group_key: str = Field(description="目标瞬间组 key（如 g2）")
