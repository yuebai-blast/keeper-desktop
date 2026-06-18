"""ProjectService 工作流编排的测试——用桩替代分组/层①/层②引擎，验证：
建项目复制副本（不动源）→ 分组落库 → 评测初始化去留 → 完成门禁 → 归档+清理 workspace。
"""

import pytest
from PIL import Image

from keeper_engine.client.geocode_client import GeocodeClient
from keeper_engine.enumeration.biz_code import BizCode
from keeper_engine.exception.errors import BizException
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
from keeper_engine.response.common import PhotoError
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


class FakeAssessLastFails:
    """组内最后一张层①失败（记入 errors、不在 scores/survivors）；其余正常。"""

    def assess(self, req) -> AssessResponse:
        paths = [p.path for p in req.photos]
        ok, bad = paths[:-1], paths[-1]
        scores = [LocalScore(path=p, score=70.0) for p in ok]
        survivors = [SurvivorEntry(path=p, score=70.0, origin=PkOrigin.PASSED) for p in ok]
        return AssessResponse(group_id=req.group_id, scores=scores, survivors=survivors,
                              n=3, m=5, errors=[PhotoError(path=bad, error="ValueError: 读图失败")])


class FakeScoringLastFails:
    """survivors 里最后一张层②失败（记入 errors、不在 pk）；第一张通过。"""

    def score(self, req) -> ScoreResponse:
        ok, bad = req.photos[:-1], req.photos[-1]
        scores = [Score(path=p, score=80.0, reason="好", flaws="") for p in ok]
        pk = [PkEntry(path=ok[0], origin=PkOrigin.PASSED, score=80.0, reason="好")] if ok else []
        return ScoreResponse(group_id=req.group_id, scores=scores, pk=pk, n=3,
                             errors=[PhotoError(path=bad, error="TimeoutError: 网络超时")])


def _build_service(tmp_path, assess, scoring):
    settings = Settings(home=tmp_path / "keeper", output_root=tmp_path / "out", geocode_enabled=False)
    db = Database(settings)
    db.create_all()
    photos = ProjectPhotoMapper(db)
    pk_mapper = PkStateMapper(db)
    pk = PkService(photos, pk_mapper)
    service = ProjectService(
        ProjectMapper(db), photos, PhotoGroupMapper(db), pk_mapper,
        FakeGrouping(), assess, scoring, pk,
        WorkspaceService(), GeocodeClient(settings, GeocodeCacheMapper(db)), settings,
    )
    return service, settings


@pytest.fixture
def svc(tmp_path):
    return _build_service(tmp_path, FakeAssess(), FakeScoring())


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
    assert project.status == "GROUPING"


def test_duplicate_name_rejected(svc, tmp_path):
    service, _ = svc
    src = _make_source(tmp_path, 2)
    service.create("dup", str(src))
    with pytest.raises(BizException) as ei:
        service.create("dup", str(src))
    assert ei.value.biz == BizCode.PROJECT_NAME_DUPLICATE


def test_delete_removes_workspace_and_db_resources(svc, tmp_path):
    """删除项目：清掉 workspace 副本 + 全部数据库资源（照片/组/PK/项目行），不动源。"""
    service, settings = svc
    src = _make_source(tmp_path, 4)
    project = service.create("待删", str(src))
    pid = project.id
    service.group(pid)
    service.assess_group(pid, "g1")
    # 起一局 PK 以产生 PkState，验证删除时一并清理
    pool = [p.workspace_path for p in service._photos.by_group(pid, "g1")]
    service._pk.start(pid, "g1", pool, False)

    ws = settings.workspace_dir / "待删"
    assert ws.is_dir()
    assert service._photos.by_project(pid) and service._groups.by_project(pid)
    assert service._pk_states.get(pid, "g1") is not None

    service.delete(pid)

    assert not ws.exists()  # 副本目录已清
    assert service._projects.get(pid) is None
    assert service._photos.by_project(pid) == []
    assert service._groups.by_project(pid) == []
    assert service._pk_states.get(pid, "g1") is None
    assert len(list(src.glob("*.jpg"))) == 4  # 源文件夹不动


def test_delete_missing_project_rejected(svc):
    service, _ = svc
    with pytest.raises(BizException) as ei:
        service.delete(99999)
    assert ei.value.biz == BizCode.PROJECT_NOT_FOUND


def test_full_flow_to_completion(svc, tmp_path):
    service, settings = svc
    src = _make_source(tmp_path, 4)
    project = service.create("流程", str(src))
    pid = project.id

    detail = service.group(pid)
    assert len(detail.groups) == 2
    assert detail.project.status == "SELECTING"

    # 评测一组：初始化去留（每组第一张通过，其余未通过）
    gd = service.assess_group(pid, "g1")
    assert gd.group.status == "ASSESSED"
    assert sum(1 for p in gd.photos if p.selection == Selection.KEPT.value) == 1
    assert any(p.selection == Selection.DISCARDED.value for p in gd.photos)
    assert all(p.local_score == 70.0 for p in gd.photos)  # 层①落库

    # 完成门禁：还有未确认分组 → GROUPS_NOT_ALL_CONFIRMED
    with pytest.raises(BizException) as ei:
        service.complete(pid)
    assert ei.value.biz == BizCode.GROUPS_NOT_ALL_CONFIRMED

    # 一键通过（会评测 g2 并全部确认）
    service.confirm_all(pid)
    after = service.get_detail(pid)
    assert all(g.status == "CONFIRMED" for g in after.groups)

    # 完成：归档「通过」到输出目录 + 删 workspace
    res = service.complete(pid)
    out = settings.output_root / "流程"
    assert res.output_dir == str(out)
    assert res.kept_count == 2  # 两组各 1 张通过
    assert out.is_dir() and len(list(out.glob("*.jpg"))) == 2
    assert not (settings.workspace_dir / "流程").exists()  # workspace 已清理
    assert service.get_detail(pid).project.status == "COMPLETED"


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


def test_layer1_failure_surfaces_and_persists_assess_error(tmp_path):
    """层①单张失败：该张写入 assess_error 并透出到 PhotoView，且退出重读仍在。"""
    service, _ = _build_service(tmp_path, FakeAssessLastFails(), FakeScoring())
    src = _make_source(tmp_path, 4)  # g1 = 前两张
    project = service.create("层一失败", str(src))
    service.group(project.id)

    gd = service.assess_group(project.id, "g1")
    failed = [p for p in gd.photos if p.assess_error]
    assert len(failed) == 1
    assert "读图失败" in failed[0].assess_error
    assert failed[0].local_score is None  # 层①失败没有分
    assert failed[0].selection == Selection.DISCARDED.value
    # 成功的图无错误
    assert all(p.assess_error is None for p in gd.photos if p.id != failed[0].id)

    # 落库持久：重新读取仍带错误
    reread = service.get_group_detail(project.id, "g1")
    assert any(p.assess_error and "读图失败" in p.assess_error for p in reread.photos)


def test_layer2_failure_surfaces_assess_error(tmp_path):
    """层②单张失败：该 survivor 写入 assess_error，最终未通过。"""
    service, _ = _build_service(tmp_path, FakeAssess(), FakeScoringLastFails())
    src = _make_source(tmp_path, 4)
    project = service.create("层二失败", str(src))
    service.group(project.id)

    gd = service.assess_group(project.id, "g1")
    failed = [p for p in gd.photos if p.assess_error]
    assert len(failed) == 1
    assert "网络超时" in failed[0].assess_error
    assert failed[0].local_score == 70.0  # 层①有分
    assert failed[0].llm_score is None     # 层②失败没有分
    assert failed[0].selection == Selection.DISCARDED.value


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
