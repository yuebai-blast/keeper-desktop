"""瞬间组实体的数据访问。复用共享 Database。"""

from __future__ import annotations

from sqlmodel import delete, select

from ..config.database import Database
from ..entity.photo_group import PhotoGroup


class PhotoGroupMapper:
    """瞬间组的批量插入与按项目读取、查单组、更新。"""

    def __init__(self, database: Database) -> None:
        self._db = database

    def bulk_create(self, groups: list[PhotoGroup]) -> None:
        with self._db.session() as session:
            session.add_all(groups)
            session.commit()

    def by_project(self, project_id: int) -> list[PhotoGroup]:
        with self._db.session() as session:
            stmt = select(PhotoGroup).where(PhotoGroup.project_id == project_id)
            return list(session.exec(stmt.order_by(PhotoGroup.id)))

    def get(self, project_id: int, group_key: str) -> PhotoGroup | None:
        with self._db.session() as session:
            stmt = select(PhotoGroup).where(
                PhotoGroup.project_id == project_id,
                PhotoGroup.group_key == group_key,
            )
            return session.exec(stmt).first()

    def update(self, group: PhotoGroup) -> PhotoGroup:
        with self._db.session() as session:
            merged = session.merge(group)
            session.commit()
            session.refresh(merged)
            return merged

    def delete(self, project_id: int, group_key: str) -> None:
        """删单个组行（移组把源组拖空后清理空组）。"""
        with self._db.session() as session:
            session.exec(delete(PhotoGroup).where(
                PhotoGroup.project_id == project_id,
                PhotoGroup.group_key == group_key,
            ))
            session.commit()

    def delete_by_project(self, project_id: int) -> None:
        """删除该项目的全部分组行（删项目时清理）。"""
        with self._db.session() as session:
            session.exec(delete(PhotoGroup).where(PhotoGroup.project_id == project_id))
            session.commit()
