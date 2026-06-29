"""project 表轻量加列迁移测试：老库缺 guarantee_* 列时，create_all 后应补齐且幂等。"""

from sqlalchemy import text

from keeper_engine.config.database import Database
from keeper_engine.config.settings import Settings


def _columns(db: Database, table: str) -> set[str]:
    with db.engine.connect() as conn:
        rows = conn.execute(text(f"PRAGMA table_info({table})")).all()
    return {r[1] for r in rows}  # PRAGMA table_info 第 1 列是列名


def test_create_all_adds_missing_guarantee_columns_to_old_table(tmp_path):
    settings = Settings(home=tmp_path / "keeper")
    db = Database(settings)
    # 模拟「老库」：先手建一个不含 guarantee_* 列的精简 project 表
    with db.engine.begin() as conn:
        conn.execute(text("CREATE TABLE project (id INTEGER PRIMARY KEY, name TEXT)"))

    db.create_all()  # 触发建表（已存在则跳过）+ 加列迁移

    cols = _columns(db, "project")
    assert "guarantee_pct" in cols
    assert "guarantee_fixed" in cols


def test_create_all_migration_is_idempotent(tmp_path):
    settings = Settings(home=tmp_path / "keeper")
    db = Database(settings)
    db.create_all()
    db.create_all()  # 第二次不应报错（列已存在则跳过）
    cols = _columns(db, "project")
    assert {"guarantee_pct", "guarantee_fixed"} <= cols
