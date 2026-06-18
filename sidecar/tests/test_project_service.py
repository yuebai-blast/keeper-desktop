"""ProjectService 工作流编排的测试——用桩替代分组/层①/层②引擎，验证：
建项目复制副本（不动源）→ 分组落库 → 评测初始化去留 → 完成门禁 → 归档+清理 workspace。
"""

import pytest
from PIL import Image

from keeper_engine.client.geocode_client import GeocodeClient
from keeper_engine.enumeration.assess_phase import AssessPhase
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
from keeper_engine.service.funnel_service import FunnelService
from keeper_engine.service.params_service import ParamsService
from keeper_engine.service.pk_service import PkService
from keeper_engine.service.progress_tracker import ProgressTracker
from keeper_engine.service.project_service import ProjectService
from keeper_engine.service.ranking_service import RankingService
from keeper_engine.service.workspace_service import WorkspaceService
from keeper_engine.vo.group import Group
from keeper_engine.vo.local_score import LocalScore
from keeper_engine.vo.pk import PkEntry
from keeper_engine.request.project_request import SelectionChange
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

    def assess(self, req, on_progress=None) -> AssessResponse:
        paths = [p.path for p in req.photos]
        scores = [LocalScore(path=p, score=70.0) for p in paths]
        survivors = [SurvivorEntry(path=p, score=70.0, origin=PkOrigin.PASSED) for p in paths]
        for _ in paths:
            if on_progress is not None:
                on_progress()
        return AssessResponse(group_id=req.group_id, scores=scores, survivors=survivors,
                              n=3, m=5, errors=[])


class FakeScoring:
    """层②：第一张给高分（≥60），其余给低分（<60）；漏斗保底数 n 决定最终通过数。
    小组（size≤n）时所有照片仍全通（巧妇难为无米之炊），需用较大源（size>n）测淘汰。"""

    def score(self, req, on_progress=None) -> ScoreResponse:
        scores = [
            Score(path=p, score=80.0 if i == 0 else 50.0, reason="好", flaws="")
            for i, p in enumerate(req.photos)
        ]
        for _ in req.photos:
            if on_progress is not None:
                on_progress()
        pk = [PkEntry(path=req.photos[0], origin=PkOrigin.PASSED, score=80.0, reason="好")]
        return ScoreResponse(group_id=req.group_id, scores=scores, pk=pk, n=3, errors=[])


class FakeAssessLastFails:
    """组内最后一张层①失败（记入 errors、不在 scores/survivors）；其余正常。"""

    def assess(self, req, on_progress=None) -> AssessResponse:
        paths = [p.path for p in req.photos]
        ok, bad = paths[:-1], paths[-1]
        scores = [LocalScore(path=p, score=70.0) for p in ok]
        survivors = [SurvivorEntry(path=p, score=70.0, origin=PkOrigin.PASSED) for p in ok]
        for _ in paths:
            if on_progress is not None:
                on_progress()
        return AssessResponse(group_id=req.group_id, scores=scores, survivors=survivors,
                              n=3, m=5, errors=[PhotoError(path=bad, error="ValueError: 读图失败")])


class CountingAssess:
    """记录每次被评测的 path，验证「不重复评分」。可指定某些 path 失败。"""

    def __init__(self, fail_paths=()):
        self.fail = set(fail_paths)
        self.scored: list[str] = []

    def assess(self, req, on_progress=None):
        ok, errs = [], []
        for ref in req.photos:
            self.scored.append(ref.path)
            if ref.path in self.fail:
                errs.append(PhotoError(path=ref.path, error="ValueError: 读图失败"))
            else:
                ok.append(LocalScore(path=ref.path, score=70.0))
            if on_progress is not None:
                on_progress()
        survivors = [SurvivorEntry(path=s.path, score=70.0, origin=PkOrigin.PASSED) for s in ok]
        return AssessResponse(group_id=req.group_id, scores=ok, survivors=survivors,
                              n=3, m=5, errors=errs)


class FakeScoringLastFails:
    """survivors 里最后一张层②失败（记入 errors、不在 pk）；第一张通过。"""

    def score(self, req, on_progress=None) -> ScoreResponse:
        ok, bad = req.photos[:-1], req.photos[-1]
        scores = [Score(path=p, score=80.0, reason="好", flaws="") for p in ok]
        pk = [PkEntry(path=ok[0], origin=PkOrigin.PASSED, score=80.0, reason="好")] if ok else []
        for _ in req.photos:
            if on_progress is not None:
                on_progress()
        return ScoreResponse(group_id=req.group_id, scores=scores, pk=pk, n=3,
                             errors=[PhotoError(path=bad, error="TimeoutError: 网络超时")])


def _build_service(tmp_path, assess, scoring):
    settings = Settings(home=tmp_path / "keeper", output_root=tmp_path / "out", geocode_enabled=False)
    db = Database(settings)
    db.create_all()
    photos = ProjectPhotoMapper(db)
    pk_mapper = PkStateMapper(db)
    pk = PkService(photos, pk_mapper)
    funnel = FunnelService()
    params = ParamsService()
    ranking = RankingService(funnel=FunnelService())
    progress = ProgressTracker()
    service = ProjectService(
        ProjectMapper(db), photos, PhotoGroupMapper(db), pk_mapper,
        FakeGrouping(), assess, scoring, pk,
        funnel, params, ranking,
        WorkspaceService(), GeocodeClient(settings, GeocodeCacheMapper(db)), settings,
        progress=progress,
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
    # 用 8 张：FakeGrouping 各给 g1/g2 各 4 张，n=3 < 4 使漏斗能淘汰低分（50.0）张。
    src = _make_source(tmp_path, 8)
    project = service.create("流程", str(src))
    pid = project.id

    detail = service.group(pid)
    assert len(detail.groups) == 2
    assert detail.project.status == "SELECTING"

    # 评测一组：初始化去留（漏斗保底 n=3，第一张 80.0 通过 + 兜底 2 张 50.0，共 3 KEPT，1 DISCARDED）
    gd = service.assess_group(pid, "g1")
    assert gd.group.status == "ASSESSED"
    assert sum(1 for p in gd.photos if p.selection == Selection.KEPT.value) == 3
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

    # 完成：归档「通过」到输出目录 + 删 workspace（两组各 3 张通过，共 6 张）
    res = service.complete(pid)
    out = settings.output_root / "流程"
    assert res.output_dir == str(out)
    assert res.kept_count == 6  # 两组各 3 张通过（漏斗保底 n=3）
    assert out.is_dir() and len(list(out.glob("*.jpg"))) == 6
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
    """层①单张失败：该张写入 assess_error 并透出到 PhotoView，且退出重读仍在。
    用 8 张：g1=4 张（3 好 + 1 失败），n=3，好图足够填满 kept，失败图（0 分）被比下去 DISCARDED。"""
    service, _ = _build_service(tmp_path, FakeAssessLastFails(), FakeScoring())
    src = _make_source(tmp_path, 8)
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
    """层②单张失败：该 survivor 写入 assess_error，最终未通过。
    用 8 张：g1=4 张（3 好 + 1 层②失败），n=3，好图足够填满 kept，失败图（0 分）被比下去 DISCARDED。"""
    service, _ = _build_service(tmp_path, FakeAssess(), FakeScoringLastFails())
    src = _make_source(tmp_path, 8)
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
    # 用 8 张：g1=4 张，n=3，FakeScoring 使第一张 80.0、其余 50.0 → 3 KEPT、1 DISCARDED
    src = _make_source(tmp_path, 8)
    project = service.create("改判", str(src))
    service.group(project.id)
    gd = service.assess_group(project.id, "g1")
    discarded = next(p for p in gd.photos if p.selection == Selection.DISCARDED.value)

    gd2 = service.update_selection(
        project.id, "g1",
        [SelectionChange(photo_id=discarded.id, selection=Selection.KEPT, rescued=True)],
    )
    flipped = next(p for p in gd2.photos if p.id == discarded.id)
    assert flipped.selection == Selection.KEPT.value and flipped.rescued is True


def test_layer1_failure_sets_status_and_zero_score_discarded(tmp_path):
    # 用 8 张：g1=4 张（3 好 + 1 失败），n=3，好图足够填满 kept，失败图（0 分）排第 4 被淘汰
    service, _ = _build_service(tmp_path, FakeAssessLastFails(), FakeScoring())
    src = _make_source(tmp_path, 8)
    project = service.create("L1", str(src))
    service.group(project.id)
    gd = service.assess_group(project.id, "g1")

    failed = [p for p in gd.photos if p.assess_status == "LAYER1_FAILED"]
    assert len(failed) == 1
    assert failed[0].local_score is None
    assert failed[0].selection == Selection.DISCARDED.value
    assert all(p.assess_status == "SUCCESS" for p in gd.photos if p.id != failed[0].id)


def test_layer2_failure_sets_status(tmp_path):
    # 用 8 张：g1=4 张（3 好 + 1 层②失败），n=3，好图足够填满 kept，失败图（0 分）排第 4 被淘汰
    service, _ = _build_service(tmp_path, FakeAssess(), FakeScoringLastFails())
    src = _make_source(tmp_path, 8)
    project = service.create("L2", str(src))
    service.group(project.id)
    gd = service.assess_group(project.id, "g1")

    failed = [p for p in gd.photos if p.assess_status == "LAYER2_FAILED"]
    assert len(failed) == 1
    assert failed[0].local_score == 70.0
    assert failed[0].llm_score is None
    assert failed[0].selection == Selection.DISCARDED.value


def test_retry_single_recovers_and_does_not_rescore_others(tmp_path):
    # g1 = 前两张；第二张层①失败
    failing = CountingAssess()
    service, _ = _build_service(tmp_path, failing, FakeScoring())
    src = _make_source(tmp_path, 4)
    project = service.create("retry", str(src))
    service.group(project.id)
    # 锁定 g1 第二张 workspace 路径作为失败目标
    g1 = service._photos.by_group(project.id, "g1")
    bad = g1[-1]
    failing.fail = {bad.workspace_path}

    gd = service.assess_group(project.id, "g1")
    assert any(p.assess_status == "LAYER1_FAILED" for p in gd.photos)
    failing.fail = set()          # 这次重试会成功
    failing.scored.clear()        # 只统计重试阶段的评分

    gd2 = service.retry_group(project.id, "g1", photo_id=bad.id)
    assert failing.scored == [bad.workspace_path]   # 只重评失败那张，别人不重评
    recovered = next(p for p in gd2.photos if p.id == bad.id)
    assert recovered.assess_status == "SUCCESS"
    assert recovered.local_score == 70.0


def test_retry_ignored_photo_is_noop_and_keeps_confirmed(tmp_path):
    """已忽略的失败图被单张重试时应是 no-op：不重评、不把已确认组降级/重置裁决。"""
    failing = CountingAssess()
    service, _ = _build_service(tmp_path, failing, FakeScoring())
    src = _make_source(tmp_path, 8)  # g1 = 前 4 张
    project = service.create("ign-retry", str(src))
    service.group(project.id)
    g1 = service._photos.by_group(project.id, "g1")
    bad = g1[-1]
    failing.fail = {bad.workspace_path}

    service.assess_group(project.id, "g1")
    service.ignore_failures(project.id, "g1")          # 忽略失败 → 解阻塞
    gd = service.confirm_group(project.id, "g1")        # 确认本组
    assert gd.group.status == "CONFIRMED"

    failing.fail = set()
    failing.scored.clear()
    gd2 = service.retry_group(project.id, "g1", photo_id=bad.id)
    assert failing.scored == []                         # 已忽略图不被重评
    assert gd2.group.status == "CONFIRMED"              # 组未被降级/重算


def test_ignore_failures_keeps_status_but_marks_ignored(tmp_path):
    service, _ = _build_service(tmp_path, FakeAssessLastFails(), FakeScoring())
    src = _make_source(tmp_path, 4)
    project = service.create("ign", str(src))
    service.group(project.id)
    service.assess_group(project.id, "g1")

    gd = service.ignore_failures(project.id, "g1")
    failed = [p for p in gd.photos if p.assess_status == "LAYER1_FAILED"]
    assert failed and all(p.assess_error_ignored for p in failed)
    # ignore 只置 ignored 标志，不改 assess_status——失败图状态仍为 LAYER1_FAILED
    assert all(p.assess_status == "LAYER1_FAILED" for p in failed)


def test_retry_nonfailed_photo_id_is_noop(tmp_path):
    """对一张已 SUCCESS 的图调 retry_group(photo_id=...)：不被重评，状态不变。"""
    failing = CountingAssess()
    service, _ = _build_service(tmp_path, failing, FakeScoring())
    src = _make_source(tmp_path, 4)
    project = service.create("retry-noop", str(src))
    service.group(project.id)

    # 首评：全部成功（fail 集合为空）
    service.assess_group(project.id, "g1")
    g1 = service._photos.by_group(project.id, "g1")
    success_photo = next(p for p in g1 if p.assess_status == "SUCCESS")

    # 清除计数，对 SUCCESS 图发起单张重试
    failing.scored.clear()
    gd = service.retry_group(project.id, "g1", photo_id=success_photo.id)

    # 该 SUCCESS 图不应触发重评
    assert failing.scored == []
    # 状态仍为 SUCCESS
    after = next(p for p in gd.photos if p.id == success_photo.id)
    assert after.assess_status == "SUCCESS"


def test_unresolved_failure_blocks_confirm_and_selection(tmp_path):
    service, _ = _build_service(tmp_path, FakeAssessLastFails(), FakeScoring())
    src = _make_source(tmp_path, 4)
    project = service.create("blk", str(src))
    service.group(project.id)
    gd = service.assess_group(project.id, "g1")
    assert gd.group.failed_count == 1

    ok = next(p for p in gd.photos if p.assess_status == "SUCCESS")
    for call in (
        lambda: service.confirm_group(project.id, "g1"),
        lambda: service.update_selection(project.id, "g1",
                                         [SelectionChange(photo_id=ok.id, selection=Selection.DISCARDED)]),
        lambda: service.confirm_all(project.id),
    ):
        with pytest.raises(BizException) as ei:
            call()
        assert ei.value.biz == BizCode.GROUP_HAS_UNRESOLVED_FAILURES

    # 忽略后解锁
    service.ignore_failures(project.id, "g1")
    assert service.confirm_group(project.id, "g1").group.status == "CONFIRMED"


def test_get_progress_idle_for_unknown_project(svc):
    service, _ = svc
    p = service.get_progress(123)
    assert p.phase == AssessPhase.IDLE.value


def test_assess_group_marks_progress_done(svc, tmp_path):
    service, _ = svc
    src = _make_source(tmp_path, 4)
    project = service.create("进度甲", str(src))
    service.group(project.id)
    service.assess_group(project.id, "g1")
    p = service.get_progress(project.id)
    assert p.phase == AssessPhase.DONE.value
    assert p.group_count == 1 and p.group_index == 1


def test_confirm_all_progress_counts_pending_groups(svc, tmp_path):
    service, _ = svc
    src = _make_source(tmp_path, 6)  # FakeGrouping 对半分成 g1/g2
    project = service.create("进度乙", str(src))
    service.group(project.id)
    service.confirm_all(project.id)
    p = service.get_progress(project.id)
    assert p.phase == AssessPhase.DONE.value
    assert p.group_count == 2  # 两组都待评测，组级总数=2
