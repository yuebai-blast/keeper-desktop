"""ProjectService 工作流编排的测试——用桩替代分组/层①/层②引擎，验证：
建项目复制副本（不动源）→ 分组落库 → 评测初始化去留 → 完成门禁 → 归档+清理 workspace。
"""

import pytest
from fastapi import HTTPException
from PIL import Image

from keeper_engine.client.geocode_client import GeocodeClient
from keeper_engine.config.database import Database
from keeper_engine.config.settings import Settings
from keeper_engine.enumeration.pk_origin import PkOrigin
from keeper_engine.enumeration.selection import Selection
from keeper_engine.mapper.geocode_cache_mapper import GeocodeCacheMapper
from keeper_engine.mapper.photo_group_mapper import PhotoGroupMapper
from keeper_engine.mapper.pk_state_mapper import PkStateMapper
from keeper_engine.mapper.project_mapper import ProjectMapper
from keeper_engine.mapper.project_photo_mapper import ProjectPhotoMapper
from keeper_engine.response.assess_response import AssessResponse, SurvivorEntry
from keeper_engine.response.group_response import GroupResponse
from keeper_engine.response.score_response import ScoreResponse
from keeper_engine.service.pk_service import PkService
from keeper_engine.service.project_service import ProjectService
from keeper_engine.service.workspace_service import WorkspaceService
from keeper_engine.vo.group import Group
from keeper_engine.vo.local_score import LocalScore
from keeper_engine.vo.pk import PkEntry
from keeper_engine.vo.score import Score


class FakeGrouping:
    """把照片对半分成 g1 / g2 两组。"""

    def group(self, req) -> GroupResponse:
        ps = req.photos
        mid = max(1, len(ps) // 2)
        groups = [Group(id="g1", photos=ps[:mid])]
        if ps[mid:]:
            groups.append(Group(id="g2", photos=ps[mid:]))
        return GroupResponse(groups=groups, errors=[])


class FakeAssess:
    """每张给本地分；全部作为 survivors 进层②。"""

    def assess(self, req) -> AssessResponse:
        paths = [p.path for p in req.photos]
        scores = [LocalScore(path=p, score=70.0) for p in paths]
        survivors = [SurvivorEntry(path=p, score=70.0, origin=PkOrigin.PASSED) for p in paths]
        return AssessResponse(group_id=req.group_id, scores=scores, survivors=survivors,
                              n=3, m=5, errors=[])


class FakeScoring:
    """层②：只让每组第一张通过（pk），其余淘汰——产出有通过有未通过。"""

    def score(self, req) -> ScoreResponse:
        scores = [Score(path=p, score=80.0, reason="好", flaws="") for p in req.photos]
        pk = [PkEntry(path=req.photos[0], origin=PkOrigin.PASSED, score=80.0, reason="好")]
        return ScoreResponse(group_id=req.group_id, scores=scores, pk=pk, n=3, errors=[])


@pytest.fixture
def svc(tmp_path):
    settings = Settings(home=tmp_path / "keeper", output_root=tmp_path / "out", geocode_enabled=False)
    db = Database(settings)
    db.create_all()
    photos = ProjectPhotoMapper(db)
    pk = PkService(photos, PkStateMapper(db))
    service = ProjectService(
        ProjectMapper(db), photos, PhotoGroupMapper(db),
        FakeGrouping(), FakeAssess(), FakeScoring(), pk,
        WorkspaceService(), GeocodeClient(settings, GeocodeCacheMapper(db)), settings,
    )
    return service, settings


def _make_source(tmp_path, n: int):
    src = tmp_path / "source"
    src.mkdir()
    for i in range(n):
        Image.new("RGB", (8, 8), (i * 20 % 255, 0, 0)).save(src / f"p{i}.jpg")
    return src


def test_create_copies_into_workspace_without_touching_source(svc, tmp_path):
    service, settings = svc
    src = _make_source(tmp_path, 4)
    project = service.create("项目甲", str(src))

    ws = settings.workspace_dir / "项目甲"
    assert ws.is_dir() and len(list(ws.glob("*.jpg"))) == 4
    assert len(list(src.glob("*.jpg"))) == 4  # 源文件夹不动
    assert project.photo_count == 4
    assert project.status == "grouping"


def test_duplicate_name_rejected(svc, tmp_path):
    service, _ = svc
    src = _make_source(tmp_path, 2)
    service.create("dup", str(src))
    with pytest.raises(HTTPException) as ei:
        service.create("dup", str(src))
    assert ei.value.status_code == 409


def test_full_flow_to_completion(svc, tmp_path):
    service, settings = svc
    src = _make_source(tmp_path, 4)
    project = service.create("流程", str(src))
    pid = project.id

    detail = service.group(pid)
    assert len(detail.groups) == 2
    assert detail.project.status == "selecting"

    # 评测一组：初始化去留（每组第一张通过，其余未通过）
    gd = service.assess_group(pid, "g1")
    assert gd.group.status == "assessed"
    assert sum(1 for p in gd.photos if p.selection == Selection.KEPT.value) == 1
    assert any(p.selection == Selection.DISCARDED.value for p in gd.photos)
    assert all(p.local_score == 70.0 for p in gd.photos)  # 层①落库

    # 完成门禁：还有未确认分组 → 400
    with pytest.raises(HTTPException) as ei:
        service.complete(pid)
    assert ei.value.status_code == 400

    # 一键通过（会评测 g2 并全部确认）
    service.confirm_all(pid)
    after = service.get_detail(pid)
    assert all(g.status == "confirmed" for g in after.groups)

    # 完成：归档「通过」到输出目录 + 删 workspace
    res = service.complete(pid)
    out = settings.output_root / "流程"
    assert res.output_dir == str(out)
    assert res.kept_count == 2  # 两组各 1 张通过
    assert out.is_dir() and len(list(out.glob("*.jpg"))) == 2
    assert not (settings.workspace_dir / "流程").exists()  # workspace 已清理
    assert service.get_detail(pid).project.status == "completed"


def test_recursive_import_uuid_rename_and_structured_restore(svc, tmp_path):
    """递归收图 + workspace 改 UUID 名 + 完成时还原原始目录树与原始文件名。"""
    service, settings = svc
    src = tmp_path / "source"
    (src / "day1").mkdir(parents=True)
    (src / "day2" / "scene").mkdir(parents=True)
    Image.new("RGB", (8, 8), (10, 0, 0)).save(src / "top.jpg")
    Image.new("RGB", (8, 8), (20, 0, 0)).save(src / "day1" / "a.jpg")
    Image.new("RGB", (8, 8), (30, 0, 0)).save(src / "day2" / "scene" / "b.jpg")

    project = service.create("嵌套", str(src))
    assert project.photo_count == 3  # 递归收齐三层

    # workspace 文件名是 UUID（不等于原始名），但扩展名保留
    ws = settings.workspace_dir / "嵌套"
    ws_names = {p.name for p in ws.glob("*.jpg")}
    assert ws_names and all(n not in {"top.jpg", "a.jpg", "b.jpg"} for n in ws_names)

    # DB 里保留了相对路径（posix），完成时据此还原
    rels = {p.original_rel_path for p in service._photos.by_project(project.id)}
    assert rels == {"top.jpg", "day1/a.jpg", "day2/scene/b.jpg"}

    # 全流程到完成
    service.group(project.id)
    service.confirm_all(project.id)
    service.complete(project.id)

    # 输出目录按相对路径还原原始树 + 原始名（kept = 每组第一张）
    out = settings.output_root / "嵌套"
    restored = {p.relative_to(out).as_posix() for p in out.rglob("*.jpg")}
    assert restored and restored <= {"top.jpg", "day1/a.jpg", "day2/scene/b.jpg"}


def test_manual_selection_override(svc, tmp_path):
    service, _ = svc
    src = _make_source(tmp_path, 4)
    project = service.create("改判", str(src))
    service.group(project.id)
    gd = service.assess_group(project.id, "g1")
    discarded = next(p for p in gd.photos if p.selection == Selection.DISCARDED.value)

    from keeper_engine.request.project_request import SelectionChange

    gd2 = service.update_selection(
        project.id, "g1",
        [SelectionChange(photo_id=discarded.id, selection=Selection.KEPT, rescued=True)],
    )
    flipped = next(p for p in gd2.photos if p.id == discarded.id)
    assert flipped.selection == Selection.KEPT.value and flipped.rescued is True
