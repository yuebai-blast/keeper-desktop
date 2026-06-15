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
    __table_args__ = {"comment": "PK 擂台进度快照：一组一行，支持中途退出后恢复"}

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
        sa_column_kwargs={"comment": "所属组编号 g1/g2…"},
    )
    state_json: dict = Field(
        default_factory=dict,
        sa_column=Column(JSON, comment="PK 进度 JSON：pool/current/kept_aside/history/done"),
    )
    updated_at: datetime = Field(
        default_factory=datetime.now,
        sa_column_kwargs={"comment": "最后更新时间"},
    )
