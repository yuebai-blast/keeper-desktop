"""PK 擂台状态实体——一组一行，每次选择 upsert，支持中途退出后恢复。

state_json 结构（见 service.pk_service）：
  {"pool": [...待对决路径队列...], "current": [a, b] 或 null,
   "kept_aside": [...已定通过、不再参与...], "history": [...供撤销...],
   "done": bool}
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class PkState(SQLModel, table=True):
    """某项目某组的 PK 进度快照。"""

    __tablename__ = "pk_state"

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(index=True)
    group_key: str = Field(index=True)
    state_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    updated_at: datetime = Field(default_factory=datetime.now)
