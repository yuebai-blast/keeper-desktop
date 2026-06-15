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

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(index=True)
    workspace_path: str            # ~/.keeper/workspace/{name}/ 下的副本绝对路径
    original_path: str             # 用户原文件路径（只读）
    filename: str
    capture_time: datetime | None = Field(default=None)
    location: str | None = Field(default=None)  # 反查到的拍摄地名（聚合到组/项目展示）
    group_key: str | None = Field(default=None, index=True)  # 分组后写入 g1/g2…

    # 层① 本地评分（必有）
    local_score: float | None = Field(default=None)
    local_detail: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))

    # 层② 大模型评分（仅层①survivors有）
    llm_score: float | None = Field(default=None)
    llm_reason: str = Field(default="")
    llm_flaws: str = Field(default="")

    # 漏斗/用户裁决
    origin: str | None = Field(default=None)      # passed / quota_fill（层②漏斗来源）
    selection: str | None = Field(default=None)   # kept / discarded
    rescued: bool = Field(default=False)          # 是否从「未通过」被用户救回
