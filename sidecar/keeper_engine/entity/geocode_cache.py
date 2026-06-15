"""地理编码缓存——经纬度→地名，避免对同一地点重复联网。"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel


class GeocodeCache(SQLModel, table=True):
    """坐标→地名缓存。coord_key 为经纬度按固定精度取整后的字符串。"""

    __tablename__ = "geocode_cache"
    __table_args__ = {"comment": "地理编码缓存：经纬度→地名，避免对同一地点重复联网"}

    coord_key: str = Field(
        primary_key=True,
        sa_column_kwargs={"comment": "经纬度按固定精度取整后的字符串（主键）"},
    )
    location: str = Field(
        default="",
        sa_column_kwargs={"comment": "反查到的地名"},
    )
    updated_at: datetime = Field(
        default_factory=datetime.now,
        sa_column_kwargs={"comment": "最后更新时间"},
    )
