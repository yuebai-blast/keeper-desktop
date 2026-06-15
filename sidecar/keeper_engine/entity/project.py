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

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    source_folder: str
    workspace_dir: str
    target_dir: str
    status: str = Field(default=ProjectStatus.GROUPING.value, index=True)
    photo_count: int = Field(default=0)
    time_start: datetime | None = Field(default=None)
    time_end: datetime | None = Field(default=None)
    location: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    completed_at: datetime | None = Field(default=None)
