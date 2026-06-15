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
    __table_args__ = {"comment": "瞬间组：分组结果 + 聚合拍摄地/时间范围 + 处理状态"}

    id: int | None = Field(
        default=None, primary_key=True,
        sa_column_kwargs={"comment": "主键"},
    )
    project_id: int = Field(
        index=True,
        sa_column_kwargs={"comment": "所属项目 id"},
    )
    group_key: str = Field(
        index=True,
        sa_column_kwargs={"comment": "组编号 g1/g2…（项目内唯一）"},
    )
    location: str | None = Field(
        default=None,
        sa_column_kwargs={"comment": "本组聚合拍摄地名（可空）"},
    )
    time_start: datetime | None = Field(
        default=None,
        sa_column_kwargs={"comment": "本组拍摄起始时间（可空）"},
    )
    time_end: datetime | None = Field(
        default=None,
        sa_column_kwargs={"comment": "本组拍摄结束时间（可空）"},
    )
    status: str = Field(
        default=GroupStatus.PENDING.value,
        sa_column_kwargs={"comment": "组处理状态：pending/assessed/confirmed 等"},
    )
