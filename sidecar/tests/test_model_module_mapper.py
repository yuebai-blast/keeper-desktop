"""模型模块状态 mapper 的测试——临时 sqlite，验证 upsert/all。"""

from keeper_engine.config.settings import Settings
from keeper_engine.mapper.model_module_mapper import ModelModuleMapper


def _mapper(tmp_path) -> ModelModuleMapper:
    return ModelModuleMapper(Settings(home=tmp_path))


def test_upsert_inserts_then_updates(tmp_path):
    m = _mapper(tmp_path)
    m.upsert("dino", "downloading", downloaded_bytes=10)
    m.upsert("dino", "ready", downloaded_bytes=20)  # 同 name → 更新
    rows = m.all()
    assert len(rows) == 1
    assert rows[0].name == "dino" and rows[0].status == "ready" and rows[0].downloaded_bytes == 20


def test_all_returns_sorted_by_name(tmp_path):
    m = _mapper(tmp_path)
    m.upsert("topiq", "error", detail="超时")
    m.upsert("dino", "ready")
    rows = m.all()
    assert [r.name for r in rows] == ["dino", "topiq"]
    assert rows[1].detail == "超时"


def test_db_file_created(tmp_path):
    _mapper(tmp_path)
    assert (tmp_path / "keeper.db").exists()
