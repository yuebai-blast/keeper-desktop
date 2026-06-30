"""项目照片实体的数据访问。复用共享 Database。"""

from __future__ import annotations

from sqlmodel import delete, select

from ..config.database import Database
from ..entity.project_photo import ProjectPhoto
from ..enumeration.assess_status import AssessStatus
from ..enumeration.selection import Selection


class ProjectPhotoMapper:
    """项目照片的批量插入与按项目/组读取、单/批更新。"""

    def __init__(self, database: Database) -> None:
        self._db = database

    def bulk_create(self, photos: list[ProjectPhoto]) -> None:
        with self._db.session() as session:
            session.add_all(photos)
            session.commit()

    def by_project(self, project_id: int) -> list[ProjectPhoto]:
        with self._db.session() as session:
            stmt = select(ProjectPhoto).where(ProjectPhoto.project_id == project_id)
            return list(session.exec(stmt.order_by(ProjectPhoto.id)))

    def by_group(self, project_id: int, group_key: str) -> list[ProjectPhoto]:
        with self._db.session() as session:
            stmt = select(ProjectPhoto).where(
                ProjectPhoto.project_id == project_id,
                ProjectPhoto.group_key == group_key,
            )
            return list(session.exec(stmt.order_by(ProjectPhoto.id)))

    def get(self, project_id: int, photo_id: int) -> ProjectPhoto | None:
        """按项目 + 主键取单张照片（移组时定位被拖照片）。"""
        with self._db.session() as session:
            stmt = select(ProjectPhoto).where(
                ProjectPhoto.project_id == project_id,
                ProjectPhoto.id == photo_id,
            )
            return session.exec(stmt).first()

    def unresolved_failures(self, project_id: int, group_key: str) -> list[ProjectPhoto]:
        """该组里「评测失败且未被忽略」的照片（用于阻塞裁决）。"""
        with self._db.session() as session:
            stmt = select(ProjectPhoto).where(
                ProjectPhoto.project_id == project_id,
                ProjectPhoto.group_key == group_key,
                ProjectPhoto.assess_status.in_(
                    [AssessStatus.LAYER1_FAILED.value, AssessStatus.LAYER2_FAILED.value]
                ),
                ProjectPhoto.assess_error_ignored == False,  # noqa: E712
            )
            return list(session.exec(stmt))

    def kept_of(self, project_id: int) -> list[ProjectPhoto]:
        """该项目所有 selection=kept 的照片（用于最终归档）。"""
        with self._db.session() as session:
            stmt = select(ProjectPhoto).where(
                ProjectPhoto.project_id == project_id,
                ProjectPhoto.selection == Selection.KEPT.value,
            )
            return list(session.exec(stmt.order_by(ProjectPhoto.id)))

    def update_many(self, photos: list[ProjectPhoto]) -> None:
        """合并保存一批照片（实例可能脱离 Session）。"""
        with self._db.session() as session:
            for p in photos:
                session.merge(p)
            session.commit()

    def delete_by_project(self, project_id: int) -> None:
        """删除该项目的全部照片行（删项目时清理）。"""
        with self._db.session() as session:
            session.exec(delete(ProjectPhoto).where(ProjectPhoto.project_id == project_id))
            session.commit()
