"""瞬间组实体——分组结果 + 每组聚合的拍摄地/时间范围 + 处理状态。

命名为 PhotoGroup 以避开值对象 vo.group.Group。
"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel

from ..enumeration.group_status import GroupStatus


class PhotoGroup(SQLModel, table=True):
    """一个项目里的一个瞬间组。group_key 为组内编号 g1/g2…（项目内唯一）。"""

    __tablename__ = "photo_group"

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(index=True)
    group_key: str = Field(index=True)
    location: str | None = Field(default=None)
    time_start: datetime | None = Field(default=None)
    time_end: datetime | None = Field(default=None)
    status: str = Field(default=GroupStatus.PENDING.value)
