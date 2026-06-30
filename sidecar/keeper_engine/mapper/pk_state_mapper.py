"""PK 擂台状态的数据访问——一组一行，每次选择 upsert。复用共享 Database。"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import delete, select

from ..config.database import Database
from ..entity.pk_state import PkState


class PkStateMapper:
    """PK 进度快照的查与 upsert。"""

    def __init__(self, database: Database) -> None:
        self._db = database

    def get(self, project_id: int, group_key: str) -> PkState | None:
        with self._db.session() as session:
            stmt = select(PkState).where(
                PkState.project_id == project_id,
                PkState.group_key == group_key,
            )
            return session.exec(stmt).first()

    def upsert(self, project_id: int, group_key: str, state_json: dict) -> PkState:
        """按 (project_id, group_key) 插入或覆盖整份状态。"""
        with self._db.session() as session:
            stmt = select(PkState).where(
                PkState.project_id == project_id,
                PkState.group_key == group_key,
            )
            row = session.exec(stmt).first()
            if row is None:
                row = PkState(project_id=project_id, group_key=group_key)
            row.state_json = state_json
            row.updated_at = datetime.now()
            session.add(row)
            session.commit()
            session.refresh(row)
            return row

    def delete(self, project_id: int, group_key: str) -> None:
        """删单个组的 PK 状态行（移组改变组成员后清除该组过期擂台状态）。"""
        with self._db.session() as session:
            session.exec(delete(PkState).where(
                PkState.project_id == project_id,
                PkState.group_key == group_key,
            ))
            session.commit()

    def delete_by_project(self, project_id: int) -> None:
        """删除该项目的全部 PK 状态行（删项目时清理）。"""
        with self._db.session() as session:
            session.exec(delete(PkState).where(PkState.project_id == project_id))
            session.commit()
