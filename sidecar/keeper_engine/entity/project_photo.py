"""项目内单张照片实体——承载副本路径、分组归属、两层评分与去留。

层①/层② 的完整明细以 JSON 列就地存放（local_detail 对应 vo.ScoreDetail），不另建表，
便于整组读取。selection 为最终去留（kept/discarded），PK / 手动可改。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class ProjectPhoto(SQLModel, table=True):
    """项目内的一张照片（workspace 副本）。"""

    __tablename__ = "project_photo"
    __table_args__ = {"comment": "项目内单张照片：副本路径、分组归属、两层评分与去留"}

    id: int | None = Field(
        default=None, primary_key=True,
        sa_column_kwargs={"comment": "主键"},
    )
    project_id: int = Field(
        index=True,
        sa_column_kwargs={"comment": "所属项目 id"},
    )
    workspace_path: str = Field(
        sa_column_kwargs={"comment": "~/.keeper/workspace/{name}/ 下的副本绝对路径"},
    )
    original_path: str = Field(
        sa_column_kwargs={"comment": "用户原文件绝对路径（只读）"},
    )
    original_rel_path: str = Field(
        sa_column_kwargs={"comment": "相对 source_folder 的相对路径（posix 风格），完成时据此还原原始目录树"},
    )
    filename: str = Field(
        sa_column_kwargs={"comment": "原始文件名（= 相对路径最后一段，展示用）"},
    )
    capture_time: datetime | None = Field(
        default=None,
        sa_column_kwargs={"comment": "EXIF 拍摄时间（可空）"},
    )
    location: str | None = Field(
        default=None,
        sa_column_kwargs={"comment": "GPS 反查到的拍摄地名（聚合到组/项目展示，可空）"},
    )
    group_key: str | None = Field(
        default=None, index=True,
        sa_column_kwargs={"comment": "所属瞬间组编号 g1/g2…（分组后写入，可空）"},
    )

    # 层① 本地评分（必有）
    local_score: float | None = Field(
        default=None,
        sa_column_kwargs={"comment": "层① 本地合成分（可空，未评测时为空）"},
    )
    local_detail: dict | None = Field(
        default=None,
        sa_column=Column(JSON, nullable=True, comment="层① 评分明细 JSON（对应 vo.ScoreDetail）"),
    )

    # 层② 大模型评分（仅层①survivors有）
    llm_score: float | None = Field(
        default=None,
        sa_column_kwargs={"comment": "层② 大模型打分（仅层① survivors 有，可空）"},
    )
    llm_reason: str = Field(
        default="",
        sa_column_kwargs={"comment": "层② 大模型打分理由"},
    )
    llm_flaws: str = Field(
        default="",
        sa_column_kwargs={"comment": "层② 大模型指出的缺陷"},
    )
    llm_editable: str = Field(
        default="",
        sa_column_kwargs={"comment": "层② 修图判定：ready/worth_editing/not_worth/unfixable（未评测为空）"},
    )
    llm_edit_advice: str = Field(
        default="",
        sa_column_kwargs={"comment": "层② 修图建议：能修怎么修 / 修不了或不划算的原因"},
    )

    # 评测状态机（驱动重试与失败阻塞）；与 assess_error/assess_error_ignored 同步维护
    assess_status: str = Field(
        default="NOT_ASSESSED",
        sa_column_kwargs={"comment": "评测状态：NOT_ASSESSED/SUCCESS/LAYER1_FAILED/LAYER2_FAILED"},
    )
    # 评测失败原因：层①或层②单张评测失败时写入（null=正常），仅用于向用户透出
    assess_error: str | None = Field(
        default=None,
        sa_column_kwargs={"comment": "层①/层②评测失败原因（null=正常；非空=该张评测失败）"},
    )
    assess_error_ignored: bool = Field(
        default=False,
        sa_column_kwargs={"comment": "用户是否忽略该失败（True=解除对本组裁决的阻塞）"},
    )

    # 漏斗/用户裁决
    origin: str | None = Field(
        default=None,
        sa_column_kwargs={"comment": "层② 漏斗来源：passed（达标）/ quota_fill（保底补足），可空"},
    )
    selection: str | None = Field(
        default=None,
        sa_column_kwargs={"comment": "最终去留：kept / discarded（可空，未裁决时为空）"},
    )
    rescued: bool = Field(
        default=False,
        sa_column_kwargs={"comment": "是否从「未通过」被用户救回"},
    )
