"""模型模块状态的数据访问（SQLModel / sqlite）。

库文件为 settings.db_path（统一数据根 ~/.keeper/keeper.db）。engine 跨线程复用（预热在后台
线程写、/health 在请求线程读），故 check_same_thread=False；每次操作新开 Session。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine, select

from ..config.settings import Settings
from ..entity.model_module import ModelModule


class ModelModuleMapper:
    """模型模块下载/加载状态的增改查。"""

    def __init__(self, settings: Settings) -> None:
        db_path = Path(settings.db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._engine = create_engine(
            f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
        )
        SQLModel.metadata.create_all(self._engine)

    def upsert(self, name: str, status: str, detail: str = "", downloaded_bytes: int = 0) -> None:
        """按 name 插入或更新一条模块状态。"""
        with Session(self._engine) as session:
            row = session.get(ModelModule, name) or ModelModule(name=name)
            row.status = status
            row.detail = detail
            row.downloaded_bytes = downloaded_bytes
            row.updated_at = datetime.now()
            session.add(row)
            session.commit()

    def all(self) -> list[ModelModule]:
        """返回全部模块状态（按 name 升序）。"""
        with Session(self._engine) as session:
            return list(session.exec(select(ModelModule).order_by(ModelModule.name)))
