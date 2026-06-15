"""模型模块的下载/加载状态实体——持久化到本地 sqlite，供前端展示与诊断。"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel


class ModelModule(SQLModel, table=True):
    """一个模型模块的下载/加载状态。

    name 为模块标识（如 dino / face_group / topiq …）；status 取
    pending（待加载）/ downloading（下载中）/ ready（就绪）/ error（失败）。
    """

    __tablename__ = "model_module"
    __table_args__ = {"comment": "模型模块下载/加载状态：供前端展示与诊断"}

    name: str = Field(
        primary_key=True,
        sa_column_kwargs={"comment": "模块标识：dino / face_group / topiq …（主键）"},
    )
    status: str = Field(
        default="pending",
        sa_column_kwargs={"comment": "状态：pending/downloading/ready/error"},
    )
    detail: str = Field(
        default="",
        sa_column_kwargs={"comment": "状态详情（如错误信息）"},
    )
    downloaded_bytes: int = Field(
        default=0,
        sa_column_kwargs={"comment": "已下载字节数"},
    )
    updated_at: datetime = Field(
        default_factory=datetime.now,
        sa_column_kwargs={"comment": "最后更新时间"},
    )
