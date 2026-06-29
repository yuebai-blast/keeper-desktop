"""项目实体——一次选片任务。名字唯一，输出目录由名字派生。"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel

from ..enumeration.project_status import ProjectStatus


class Project(SQLModel, table=True):
    """一次选片任务的全局状态。

    source_folder 为用户原文件夹（只读，不动）；workspace_dir 为副本目录
    （~/.keeper/workspace/{name}）；target_dir 为最终归档目录（~/Pictures/Keeper/{name}）。
    time_start/time_end/location 是导入时聚合的拍摄时间范围与拍摄地（尽力而为，可空）。
    """

    __tablename__ = "project"
    __table_args__ = {"comment": "选片项目：一次选片任务的全局状态"}

    id: int | None = Field(
        default=None, primary_key=True,
        sa_column_kwargs={"comment": "主键"},
    )
    name: str = Field(
        index=True, unique=True,
        sa_column_kwargs={"comment": "项目名（唯一），输出目录由它派生"},
    )
    source_folder: str = Field(
        sa_column_kwargs={"comment": "用户原文件夹绝对路径（只读，不修改）"},
    )
    workspace_dir: str = Field(
        sa_column_kwargs={"comment": "副本工作目录 ~/.keeper/workspace/{name}"},
    )
    target_dir: str = Field(
        sa_column_kwargs={"comment": "最终归档目录 ~/Pictures/Keeper/{name}"},
    )
    status: str = Field(
        default=ProjectStatus.GROUPING.value, index=True,
        sa_column_kwargs={"comment": "项目状态：grouping/assessing/reviewing/completed 等"},
    )
    photo_count: int = Field(
        default=0,
        sa_column_kwargs={"comment": "导入照片总数"},
    )
    time_start: datetime | None = Field(
        default=None,
        sa_column_kwargs={"comment": "聚合的拍摄起始时间（可空）"},
    )
    time_end: datetime | None = Field(
        default=None,
        sa_column_kwargs={"comment": "聚合的拍摄结束时间（可空）"},
    )
    location: str | None = Field(
        default=None,
        sa_column_kwargs={"comment": "聚合的拍摄地名（GPS 反查，尽力而为，可空）"},
    )
    created_at: datetime = Field(
        default_factory=datetime.now,
        sa_column_kwargs={"comment": "创建时间"},
    )
    updated_at: datetime = Field(
        default_factory=datetime.now,
        sa_column_kwargs={"comment": "最后更新时间"},
    )
    completed_at: datetime | None = Field(
        default=None,
        sa_column_kwargs={"comment": "完成（归档）时间（可空）"},
    )
    guarantee_pct: float = Field(
        default=0.2,
        sa_column_kwargs={"comment": "保底百分比（小数，0<pct<=1）：每组保底数 N = max(ceil(总数×此值), 固定值)"},
    )
    guarantee_fixed: int = Field(
        default=3,
        sa_column_kwargs={"comment": "保底固定值（>=1）：每组保底数 N 的下界，小组靠它兜底"},
    )
