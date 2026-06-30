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
    """把照片对半分成 g1 / g2 两组；按张回调 on_progress、切聚类回调 on_cluster。"""

    def group(self, req, on_progress=None, on_cluster=None) -> GroupResponse:
        ps = req.photos
        for _ in ps:
            if on_progress is not None:
                on_progress()
        if on_cluster is not None:
            on_cluster()
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
    """层②：第一张给高分（≥60）并标为杂图，其余给低分（<60）；漏斗保底数 n 决定最终通过数。
    小组（size≤n）时所有照片仍全通（巧妇难为无米之炊），需用较大源（size>n）测淘汰。"""

    def score(self, req, on_progress=None) -> ScoreResponse:
        scores = [
            Score(path=p, score=80.0 if i == 0 else 50.0, reason="好", flaws="", is_junk=(i == 0))
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


@pytest.mark.parametrize(
    "bad_name",
    [
        "", "   ",                                  # 空 / 纯空白
        "a/b", "a\\b", ".", "..", "x\x00y",         # 路径分隔符 / 穿越 / 空字节
        "a" * 101,                                  # 过长
        "a<b", "a>b", "a:b", 'a"b', "a|b", "a?b", "a*b",  # Win 禁用字符
        "trip.",                                    # 结尾点（Win 会吞掉）
        "CON", "con", "nul", "COM1", "LPT9", "PRN.txt",   # Win 保留设备名（含带扩展名）
        "婚礼.app", "x.App", "y.bundle", "z.FRAMEWORK",    # mac 包后缀（大小写不敏感）
    ],
)
def test_invalid_project_name_rejected(bad_name):
    with pytest.raises(BizException) as ei:
        ProjectService._validate_name(bad_name)
    assert ei.value.biz == BizCode.INVALID_PROJECT_NAME


@pytest.mark.parametrize(
    "good_name",
    # 不能误伤：含 app/com 但非保留名/非包后缀、带普通扩展名、编号超出保留范围的名字
    ["项目甲", "林岚婚礼-上午", "report v2", "COM0", "LPT10", "app store 素材", "a.jpg 整理"],
)
def test_valid_project_name_accepted(good_name):
    assert ProjectService._validate_name(good_name) == good_name.strip()


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


def test_llm_is_junk_persisted(svc, tmp_path):
    """FakeScoring 把每组第一张标为杂图；该张应落库为 llm_is_junk=True，其余 False。"""
    service, _ = svc
    src = _make_source(tmp_path, 6)
    pid = service.create("p", str(src)).id
    service.group(pid)
    gd = service.assess_group(pid, "g1")
    # FakeScoring 把每组第一张标为杂图；该张应落库为 llm_is_junk=True，其余 False
    junk = [p for p in gd.photos if p.llm_is_junk]
    assert len(junk) == 1
    assert all(not p.llm_is_junk for p in gd.photos if p.id != junk[0].id)


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


# ── 二次预览（项目级跨组去留）──────────────────────────────────────────────


def test_get_review_partitions_and_sorts(svc, tmp_path):
    service, _ = svc
    src = _make_source(tmp_path, 6)
    pid = service.create("p", str(src)).id
    service.group(pid)
    service.assess_group(pid, "g1")
    service.assess_group(pid, "g2")
    rv = service.get_review(pid)
    # kept/discarded 互补、覆盖全部照片
    all_ids = {p.id for p in service._photos.by_project(pid)}
    assert {p.id for p in rv.kept} | {p.id for p in rv.discarded} == all_ids
    assert all(p.selection == Selection.KEPT.value for p in rv.kept)
    # discarded 区契约是 != KEPT（含 None），断言对齐实现而非假设所有弃图均已被标为 DISCARDED
    assert all(p.selection != Selection.KEPT.value for p in rv.discarded)
    # 区内按组号升序、组内层②分降序
    keys = [(p.group_key, -(p.llm_score or 0.0)) for p in rv.kept]
    assert keys == sorted(keys)


def test_update_selection_batch_flips(svc, tmp_path):
    service, _ = svc
    src = _make_source(tmp_path, 6)
    pid = service.create("p", str(src)).id
    service.group(pid)
    service.assess_group(pid, "g1")
    service.assess_group(pid, "g2")
    rv = service.get_review(pid)
    flip_ids = [rv.kept[0].id]
    rv2 = service.update_selection_batch(pid, flip_ids, Selection.DISCARDED)
    assert flip_ids[0] in {p.id for p in rv2.discarded}
    assert flip_ids[0] not in {p.id for p in rv2.kept}


def test_get_review_missing_project_rejected(svc):
    service, _ = svc
    with pytest.raises(BizException):
        service.get_review(999999)


def test_get_review_none_selection_falls_into_discarded(svc, tmp_path):
    """selection=None 的照片必须落入 discarded 区、不在 kept 区。
    这是 get_review 实现契约（discarded = selection != KEPT，含 None 兜底）的关键验证。"""
    service, _ = svc
    src = _make_source(tmp_path, 6)
    pid = service.create("p", str(src)).id
    service.group(pid)
    service.assess_group(pid, "g1")
    service.assess_group(pid, "g2")

    # 从任意组取一张已有去留的照片，直接把 selection 置 None 落库
    all_photos = service._photos.by_project(pid)
    target = all_photos[0]
    target.selection = None
    service._photos.update_many([target])

    rv = service.get_review(pid)

    kept_ids = {p.id for p in rv.kept}
    discarded_ids = {p.id for p in rv.discarded}

    # selection=None 的照片必须出现在 discarded 区
    assert target.id in discarded_ids, "selection=None 的照片未落入 discarded 区"
    # 且不在 kept 区（两区严格互补）
    assert target.id not in kept_ids, "selection=None 的照片不应出现在 kept 区"


def test_group_reports_progress_done(svc, tmp_path):
    service, _ = svc
    src = _make_source(tmp_path, 4)
    project = service.create("分组进度", str(src))
    service.group(project.id)
    # 分组跑完后，共享进度侧信道停在 DONE（begin→tick→phase(CLUSTER)→done 全走过）
    assert service.get_progress(project.id).phase == AssessPhase.DONE.value


# ── 保底旋钮（guarantee knobs）──────────────────────────────────────────────


def test_create_persists_default_guarantee_knobs(svc, tmp_path):
    service, _ = svc
    src = _make_source(tmp_path, 4)
    project = service.create("默认旋钮", str(src))
    assert project.guarantee_pct == 0.2
    assert project.guarantee_fixed == 3


def test_create_persists_custom_guarantee_knobs(svc, tmp_path):
    service, settings = svc
    src = _make_source(tmp_path, 4)
    service.create("自定义旋钮", str(src), guarantee_pct=30, guarantee_fixed=5)
    # 百分比以整数入参、以小数落库
    from keeper_engine.config.database import Database
    db = Database(settings)
    row = ProjectMapper(db).get_by_name("自定义旋钮")
    assert row.guarantee_pct == 0.3
    assert row.guarantee_fixed == 5


def test_create_rejects_out_of_range_guarantee_pct(svc, tmp_path):
    service, _ = svc
    src = _make_source(tmp_path, 4)
    with pytest.raises(BizException) as ei:
        service.create("非法百分比", str(src), guarantee_pct=0)
    assert ei.value.biz == BizCode.INVALID_GUARANTEE_PARAMS


def test_create_rejects_out_of_range_guarantee_fixed(svc, tmp_path):
    service, _ = svc
    src = _make_source(tmp_path, 4)
    with pytest.raises(BizException) as ei:
        service.create("非法固定值", str(src), guarantee_fixed=0)
    assert ei.value.biz == BizCode.INVALID_GUARANTEE_PARAMS


def _count_kept_in_group(settings, project_id: int, group_key: str) -> int:
    from keeper_engine.config.database import Database
    db = Database(settings)
    photos = ProjectPhotoMapper(db).by_project(project_id)
    return sum(
        1 for p in photos
        if p.group_key == group_key and p.selection == Selection.KEPT.value
    )


def test_assess_kept_count_follows_project_guarantee_fixed(tmp_path):
    # 源 10 张 → FakeGrouping 对半分成 g1(5)/g2(5)。固定值越大，保底越多 → KEPT 越多。
    src = _make_source(tmp_path, 10)

    svc_lo, set_lo = _build_service(tmp_path / "lo", FakeAssess(), FakeScoring())
    p_lo = svc_lo.create("低保底", str(src), guarantee_pct=20, guarantee_fixed=1)
    svc_lo.group(p_lo.id)
    svc_lo.assess_group(p_lo.id, "g1")

    svc_hi, set_hi = _build_service(tmp_path / "hi", FakeAssess(), FakeScoring())
    p_hi = svc_hi.create("高保底", str(src), guarantee_pct=20, guarantee_fixed=3)
    svc_hi.group(p_hi.id)
    svc_hi.assess_group(p_hi.id, "g1")

    kept_lo = _count_kept_in_group(set_lo, p_lo.id, "g1")
    kept_hi = _count_kept_in_group(set_hi, p_hi.id, "g1")
    assert kept_lo == 1   # N = max(ceil(5×0.2)=1, 1) = 1
    assert kept_hi == 3   # N = max(ceil(5×0.2)=1, 3) = 3


def test_photo_mapper_get_and_group_delete(svc, tmp_path):
    """mapper 新增：按 id 取单张照片；按 group_key 删单个组。"""
    service, _ = svc
    src = _make_source(tmp_path, 4)
    pid = service.create("mapper试", str(src)).id
    service.group(pid)  # FakeGrouping → g1 / g2

    g1_photos = service._photos.by_group(pid, "g1")
    one = g1_photos[0]
    # get：命中返回该张；未命中返回 None
    assert service._photos.get(pid, one.id).id == one.id
    assert service._photos.get(pid, 999999) is None
    # delete：删 g1 组行后，by_project 的组里不再含 g1（照片行不受影响）
    service._groups.delete(pid, "g1")
    keys = {g.group_key for g in service._groups.by_project(pid)}
    assert "g1" not in keys and "g2" in keys


def test_group_summary_exposes_aligned_photo_ids(svc, tmp_path):
    """GroupSummary.photo_ids 与 photo_paths 同序对齐，供前端缩略图发起移动。"""
    service, _ = svc
    src = _make_source(tmp_path, 4)
    pid = service.create("ids试", str(src)).id
    service.group(pid)

    detail = service.get_detail(pid)
    g1 = next(g for g in detail.groups if g.group_key == "g1")
    by_path = {p.workspace_path: p.id for p in service._photos.by_group(pid, "g1")}
    assert len(g1.photo_ids) == len(g1.photo_paths)
    assert g1.photo_ids == [by_path[path] for path in g1.photo_paths]


# ── 照片移组（move_photo）──────────────────────────────────────────────────────


def _project_with_two_groups(service, tmp_path, n=4):
    src = _make_source(tmp_path, n)
    pid = service.create(f"移组{n}", str(src)).id
    service.group(pid)  # → g1 / g2
    return pid


def test_move_assessed_photo_between_assessed_groups_keeps_scores(tmp_path):
    """case 3：已评图 → 已评组，放行，只改 group_key，评分原样保留。"""
    service, _ = _build_service(tmp_path, FakeAssess(), FakeScoring())
    pid = _project_with_two_groups(service, tmp_path, 4)
    service.assess_group(pid, "g1")
    service.assess_group(pid, "g2")
    p = service._photos.by_group(pid, "g1")[0]
    before_local, before_llm = p.local_score, p.llm_score

    service.move_photo(pid, p.id, "g2")

    moved = service._photos.get(pid, p.id)
    assert moved.group_key == "g2"
    assert moved.local_score == before_local and moved.llm_score == before_llm


def test_move_unassessed_into_pending_group_allowed(tmp_path):
    """case 1/2：未评/已评图 → 未评组（PENDING），放行。"""
    service, _ = _build_service(tmp_path, FakeAssess(), FakeScoring())
    pid = _project_with_two_groups(service, tmp_path, 4)  # 两组都 PENDING
    p = service._photos.by_group(pid, "g1")[0]
    service.move_photo(pid, p.id, "g2")
    assert service._photos.get(pid, p.id).group_key == "g2"


def test_move_unassessed_into_assessed_group_rejected(tmp_path):
    """case 4：未评图 → 已评组，拒绝 PHOTO_MOVE_TARGET_ASSESSED。"""
    service, _ = _build_service(tmp_path, FakeAssess(), FakeScoring())
    pid = _project_with_two_groups(service, tmp_path, 4)
    service.assess_group(pid, "g2")  # g2 ASSESSED；g1 仍 PENDING（照片 NOT_ASSESSED）
    p = service._photos.by_group(pid, "g1")[0]
    with pytest.raises(BizException) as ei:
        service.move_photo(pid, p.id, "g2")
    assert ei.value.biz == BizCode.PHOTO_MOVE_TARGET_ASSESSED


def test_move_into_confirmed_group_rejected(tmp_path):
    """① 已确认锁定（目标）：拒绝 GROUP_CONFIRMED_LOCKED。"""
    service, _ = _build_service(tmp_path, FakeAssess(), FakeScoring())
    pid = _project_with_two_groups(service, tmp_path, 4)
    service.assess_group(pid, "g2")
    service.confirm_group(pid, "g2")
    p = service._photos.by_group(pid, "g1")[0]
    with pytest.raises(BizException) as ei:
        service.move_photo(pid, p.id, "g2")
    assert ei.value.biz == BizCode.GROUP_CONFIRMED_LOCKED


def test_move_out_of_confirmed_group_rejected(tmp_path):
    """① 已确认锁定（源）：拒绝 GROUP_CONFIRMED_LOCKED。"""
    service, _ = _build_service(tmp_path, FakeAssess(), FakeScoring())
    pid = _project_with_two_groups(service, tmp_path, 4)
    service.assess_group(pid, "g1")
    service.confirm_group(pid, "g1")
    p = service._photos.by_group(pid, "g1")[0]
    with pytest.raises(BizException) as ei:
        service.move_photo(pid, p.id, "g2")
    assert ei.value.biz == BizCode.GROUP_CONFIRMED_LOCKED


def test_move_unresolved_failure_rejected(tmp_path):
    """② 未解决失败：拒绝 PHOTO_MOVE_BLOCKED_BY_FAILURE。"""
    service, _ = _build_service(tmp_path, FakeAssessLastFails(), FakeScoring())
    pid = _project_with_two_groups(service, tmp_path, 4)
    service.assess_group(pid, "g1")  # g1 最后一张 LAYER1_FAILED、未忽略
    bad = next(p for p in service._photos.by_group(pid, "g1")
               if p.assess_status == "LAYER1_FAILED")
    with pytest.raises(BizException) as ei:
        service.move_photo(pid, bad.id, "g2")
    assert ei.value.biz == BizCode.PHOTO_MOVE_BLOCKED_BY_FAILURE


def test_move_ignored_failure_into_pending_allowed(tmp_path):
    """case 5 细化：已忽略的失败图视为已解决，移入 PENDING 组放行。"""
    service, _ = _build_service(tmp_path, FakeAssessLastFails(), FakeScoring())
    src = _make_source(tmp_path, 6)
    pid = service.create("忽略移组", str(src)).id
    service.group(pid)                 # g1=3 张、g2=3 张
    service.assess_group(pid, "g1")    # g1 最后一张 LAYER1_FAILED
    bad = next(p for p in service._photos.by_group(pid, "g1")
               if p.assess_status == "LAYER1_FAILED")
    service.ignore_failures(pid, "g1", bad.id)  # 置 ignored，解阻塞
    service.move_photo(pid, bad.id, "g2")        # g2 仍 PENDING → 放行
    assert service._photos.get(pid, bad.id).group_key == "g2"


def test_move_same_group_is_noop(tmp_path):
    """④ 同组：no-op，成功返回、group_key 不变、不抛错。"""
    service, _ = _build_service(tmp_path, FakeAssess(), FakeScoring())
    pid = _project_with_two_groups(service, tmp_path, 4)
    p = service._photos.by_group(pid, "g1")[0]
    service.move_photo(pid, p.id, "g1")
    assert service._photos.get(pid, p.id).group_key == "g1"


def test_move_emptying_source_deletes_it(tmp_path):
    """⑤ 放行后源组被拖空（0 张）→ 删除空组。"""
    service, _ = _build_service(tmp_path, FakeAssess(), FakeScoring())
    pid = _project_with_two_groups(service, tmp_path, 2)  # g1 一张、g2 一张
    only = service._photos.by_group(pid, "g1")[0]
    service.move_photo(pid, only.id, "g2")
    keys = {g.group_key for g in service._groups.by_project(pid)}
    assert "g1" not in keys and "g2" in keys


def test_move_photo_not_found(tmp_path):
    service, _ = _build_service(tmp_path, FakeAssess(), FakeScoring())
    pid = _project_with_two_groups(service, tmp_path, 4)
    with pytest.raises(BizException) as ei:
        service.move_photo(pid, 999999, "g2")
    assert ei.value.biz == BizCode.PHOTO_NOT_FOUND


def test_move_target_group_not_found(tmp_path):
    service, _ = _build_service(tmp_path, FakeAssess(), FakeScoring())
    pid = _project_with_two_groups(service, tmp_path, 4)
    p = service._photos.by_group(pid, "g1")[0]
    with pytest.raises(BizException) as ei:
        service.move_photo(pid, p.id, "g_missing")
    assert ei.value.biz == BizCode.GROUP_NOT_FOUND


def test_move_clears_source_pk_state(tmp_path):
    """移组后源组的进行中 PK 状态应被清除（成员已变、擂台已过期）。
    用 4 张（g1/g2 各 2 张），移后 g1 仍剩 1 张非空，不触发删组，
    专门验证「源组非空分支」下 PkState 也被清除。"""
    service, _ = _build_service(tmp_path, FakeAssess(), FakeScoring())
    pid = _project_with_two_groups(service, tmp_path, 4)  # g1=2 张，g2=2 张
    # 给 g1 起一局 PK 擂台
    pool = [p.workspace_path for p in service._photos.by_group(pid, "g1")]
    service._pk.start(pid, "g1", pool, False)
    # 移动前 PkState 存在
    assert service._pk_states.get(pid, "g1") is not None
    # 把 g1 一张移到 g2（g1 仍剩 1 张，非空）
    photo = service._photos.by_group(pid, "g1")[0]
    service.move_photo(pid, photo.id, "g2")
    # 移动后 g1 的 PK 状态应被清除
    assert service._pk_states.get(pid, "g1") is None


def test_move_clears_target_pk_state(tmp_path):
    """移组后目标组的进行中 PK 状态应被清除（新成员进入、擂台已过期）。"""
    service, _ = _build_service(tmp_path, FakeAssess(), FakeScoring())
    pid = _project_with_two_groups(service, tmp_path, 4)  # g1=2 张，g2=2 张
    # 给 g2 起一局 PK 擂台
    pool = [p.workspace_path for p in service._photos.by_group(pid, "g2")]
    service._pk.start(pid, "g2", pool, False)
    # 移动前 g2 PkState 存在
    assert service._pk_states.get(pid, "g2") is not None
    # 把 g1 一张移到 g2
    photo = service._photos.by_group(pid, "g1")[0]
    service.move_photo(pid, photo.id, "g2")
    # 移动后 g2 的 PK 状态应被清除
    assert service._pk_states.get(pid, "g2") is None
