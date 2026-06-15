"""PK 擂台状态机的测试——四种结局、守擂、收口与撤销，以及去留写回。"""

import pytest

from keeper_engine.config.database import Database
from keeper_engine.config.settings import Settings
from keeper_engine.entity.project_photo import ProjectPhoto
from keeper_engine.enumeration.pk_outcome import PkOutcome
from keeper_engine.enumeration.selection import Selection
from keeper_engine.mapper.pk_state_mapper import PkStateMapper
from keeper_engine.mapper.project_photo_mapper import ProjectPhotoMapper
from keeper_engine.service.pk_service import PkService

PID = 1
GK = "g1"


@pytest.fixture
def ctx(tmp_path):
    db = Database(Settings(home=tmp_path))
    db.create_all()
    photos = ProjectPhotoMapper(db)
    pk = PkService(photos, PkStateMapper(db))
    return photos, pk


def _seed(photos: ProjectPhotoMapper, names: list[str]) -> None:
    photos.bulk_create([
        ProjectPhoto(project_id=PID, workspace_path=n, original_path=n, original_rel_path=n, filename=n, group_key=GK)
        for n in names
    ])


def _selection(photos: ProjectPhotoMapper) -> dict[str, str | None]:
    return {p.workspace_path: p.selection for p in photos.by_group(PID, GK)}


def test_pick_winner_stays_and_loser_discarded(ctx):
    """二选一：胜者守擂迎下一张，败者淘汰；最后守擂者通过。"""
    photos, pk = ctx
    _seed(photos, ["a", "b", "c"])
    view = pk.start(PID, GK, ["a", "b", "c"], restart=False)
    assert view.current == ["a", "b"]

    view = pk.choose(PID, GK, PkOutcome.PICK_LEFT)   # a 胜 b，a 迎 c
    assert view.current == ["a", "c"]
    view = pk.choose(PID, GK, PkOutcome.PICK_RIGHT)  # c 胜 a，pool 空 → c 通过
    assert view.done is True

    sel = _selection(photos)
    assert sel == {"a": Selection.DISCARDED.value, "b": Selection.DISCARDED.value,
                   "c": Selection.KEPT.value}


def test_keep_both_then_fresh_pair(ctx):
    """都选：两张都通过、不再参与，下一对取两张新图。"""
    photos, pk = ctx
    _seed(photos, ["a", "b", "c", "d"])
    pk.start(PID, GK, ["a", "b", "c", "d"], restart=False)
    view = pk.choose(PID, GK, PkOutcome.KEEP_BOTH)   # a,b 通过；下一对 c,d
    assert view.current == ["c", "d"]
    view = pk.choose(PID, GK, PkOutcome.DROP_BOTH)    # c,d 淘汰；pool 空 → 结束
    assert view.done is True
    sel = _selection(photos)
    assert sel == {"a": Selection.KEPT.value, "b": Selection.KEPT.value,
                   "c": Selection.DISCARDED.value, "d": Selection.DISCARDED.value}


def test_drop_both_with_lone_remainder_kept(ctx):
    """都不选后只剩 1 张：无对手，按通过收下并结束。"""
    photos, pk = ctx
    _seed(photos, ["a", "b", "c"])
    pk.start(PID, GK, ["a", "b", "c"], restart=False)
    view = pk.choose(PID, GK, PkOutcome.DROP_BOTH)   # a,b 淘汰；只剩 c → c 通过、结束
    assert view.done is True
    sel = _selection(photos)
    assert sel == {"a": Selection.DISCARDED.value, "b": Selection.DISCARDED.value,
                   "c": Selection.KEPT.value}


def test_undo_reverts_to_previous_pair(ctx):
    """撤销回到上一对，且不改变（PK 中本就未写）selection。"""
    photos, pk = ctx
    _seed(photos, ["a", "b", "c"])
    pk.start(PID, GK, ["a", "b", "c"], restart=False)
    pk.choose(PID, GK, PkOutcome.PICK_LEFT)          # a 迎 c
    view = pk.undo(PID, GK)
    assert view.current == ["a", "b"]
    assert view.can_undo is False
    assert all(s is None for s in _selection(photos).values())


def test_resume_returns_existing_progress(ctx):
    """有未完成进度且非 restart → 恢复，不重开。"""
    photos, pk = ctx
    _seed(photos, ["a", "b", "c"])
    pk.start(PID, GK, ["a", "b", "c"], restart=False)
    pk.choose(PID, GK, PkOutcome.PICK_LEFT)          # 推进到 a,c
    resumed = pk.start(PID, GK, ["x", "y"], restart=False)  # pool 应被忽略
    assert resumed.current == ["a", "c"]


def test_single_photo_pool_auto_kept(ctx):
    """池中只有 1 张：无需对决直接通过、结束。"""
    photos, pk = ctx
    _seed(photos, ["a"])
    view = pk.start(PID, GK, ["a"], restart=False)
    assert view.done is True
    assert _selection(photos)["a"] == Selection.KEPT.value
