"""共享 SQLite 引擎：全部 mapper 复用同一 engine（统一数据根 ~/.keeper/keeper.db）。

engine 跨线程复用（预热在后台线程写、请求线程读、工作流在请求线程读写），故
check_same_thread=False；每次操作新开 Session。建表统一走 create_all()——app 启动时调一次，
调用前 import 全部实体以完成 SQLModel 元数据注册。
"""

from __future__ import annotations

from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

from .settings import Settings


class Database:
    """持有共享 engine，提供 Session 与建表。由 DI 以单例注入各 mapper。"""

    def __init__(self, settings: Settings) -> None:
        db_path = Path(settings.db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
        )

    def create_all(self) -> None:
        """建立全部已注册的 SQLModel 表（先 import 实体包，确保元数据已注册）。"""
        from .. import entity  # noqa: F401 —— 触发各实体模块导入，注册到 SQLModel.metadata

        SQLModel.metadata.create_all(self.engine)

    def session(self) -> Session:
        """新开一个 Session（调用方用 with 管理生命周期）。"""
        return Session(self.engine)
