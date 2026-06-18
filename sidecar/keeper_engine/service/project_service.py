"""项目工作流编排——持久化权威 + 文件操作 + 复用现有两层评分引擎。

把零散的引擎能力（分组 / 层① / 层②）串成可持久化、可恢复的「项目」流程：
  preview → create（复制副本）→ group（分组）→ assess_group（层①+层②，初始化去留）
  → update_selection / PK（用户裁决）→ confirm_group → complete（归档+清理 workspace）。

照片不出本地：只动 workspace 副本与输出目录，绝不写源文件夹；拍摄地只把坐标交给在线反查。
不静默降级：本地模型未就绪（MODEL_NOT_READY）、大模型不可用（SCORER_FAILED）由所复用的引擎 service 抛出，这里不吞。
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from PIL import Image

from ..client.geocode_client import GeocodeClient
from ..config.settings import Settings
from ..enumeration.assess_phase import AssessPhase
from ..enumeration.biz_code import BizCode
from ..entity.photo_group import PhotoGroup
from ..entity.project import Project
from ..entity.project_photo import ProjectPhoto
from ..enumeration.group_status import GroupStatus
from ..enumeration.project_status import ProjectStatus
from ..enumeration.selection import Selection
from ..exception.errors import BizException
from ..mapper.photo_group_mapper import PhotoGroupMapper
from ..mapper.pk_state_mapper import PkStateMapper
from ..mapper.project_mapper import ProjectMapper
from ..mapper.project_photo_mapper import ProjectPhotoMapper
from ..request.assess_request import AssessRequest, PhotoRef
from ..request.group_request import GroupRequest
from ..request.project_request import SelectionChange
from ..request.score_request import ScoreRequest
from ..response.common import PhotoError
from ..response.project_response import (
    AssessProgress,
    CompleteResponse,
    GroupDetailResponse,
    GroupSummary,
    PhotoView,
    ProjectDetailResponse,
    ProjectPreviewResponse,
    ProjectView,
)
from ..util import imaging
from ..enumeration.assess_status import AssessStatus
from ..vo.local_score import LocalScore
from ..vo.score import Score
from .assess_service import AssessService
from .funnel_service import FunnelService
from .grouping_service import GroupingService
from .params_service import ParamsService
from .pk_service import PkService
from .progress_tracker import ProgressTracker
from .ranking_service import RankingService
from .scoring_service import ScoringService
from .workspace_service import WorkspaceService


class ProjectService:
    """项目工作流编排核心。"""

    def __init__(
        self,
        project_mapper: ProjectMapper,
        photo_mapper: ProjectPhotoMapper,
        group_mapper: PhotoGroupMapper,
        pk_mapper: PkStateMapper,
        grouping: GroupingService,
        assess: AssessService,
        scoring: ScoringService,
        pk: PkService,
        funnel: FunnelService,
        params: ParamsService,
        ranking: RankingService,
        workspace: WorkspaceService,
        geocode: GeocodeClient,
        settings: Settings,
        progress: ProgressTracker | None = None,
    ) -> None:
        self._projects = project_mapper
        self._photos = photo_mapper
        self._groups = group_mapper
        self._pk_states = pk_mapper
        self._grouping = grouping
        self._assess = assess
        self._scoring = scoring
        self._pk = pk
        self._funnel = funnel
        self._params = params
        self._ranking = ranking
        self._workspace = workspace
        self._geocode = geocode
        self._settings = settings
        self._progress = progress or ProgressTracker()  # 缺省自建仅兼容老式构造，不参与跨请求共享

    # ── 页面一：预览 + 创建 ──────────────────────────────────────────────────

    def preview(self, folder: str) -> ProjectPreviewResponse:
        """扫描源文件夹：统计数量、拍摄时间范围、拍摄地（不建项目，不复制）。"""
        try:
            files = self._workspace.scan_images(folder)
        except (NotADirectoryError, FileNotFoundError) as e:
            raise BizException(BizCode.INVALID_SOURCE_FOLDER, str(e)) from e

        times: list[datetime] = []
        locations: list[str] = []
        errors: list[PhotoError] = []
        for f in files:
            t, loc, err = self._extract(str(f))
            if err:
                errors.append(PhotoError(path=str(f), error=err))
            if t:
                times.append(t)
            if loc:
                locations.append(loc)

        return ProjectPreviewResponse(
            count=len(files),
            time_start=min(times) if times else None,
            time_end=max(times) if times else None,
            location=self._most_common(locations),
            errors=errors,
        )

    def create(self, name: str, source_folder: str) -> ProjectView:
        """新建项目：校验名唯一 → 复制副本到 workspace → 落库照片与时间/拍摄地。"""
        name = self._validate_name(name)
        if self._projects.get_by_name(name):
            raise BizException(BizCode.PROJECT_NAME_DUPLICATE, f"项目名已存在：{name}")
        try:
            files = self._workspace.scan_images(source_folder)
        except (NotADirectoryError, FileNotFoundError) as e:
            raise BizException(BizCode.INVALID_SOURCE_FOLDER, str(e)) from e
        if not files:
            raise BizException(BizCode.NO_IMPORTABLE_IMAGES)

        workspace_dir = str(self._settings.workspace_dir / name)
        target_dir = str(self._settings.output_root / name)
        mapping = self._workspace.copy_into([str(f) for f in files], workspace_dir)

        base = Path(source_folder)
        rows: list[ProjectPhoto] = []
        times: list[datetime] = []
        locations: list[str] = []
        for src, dest in mapping:
            t, loc, _ = self._extract(dest)
            if t:
                times.append(t)
            if loc:
                locations.append(loc)
            rel = Path(src).relative_to(base).as_posix()  # 相对源根的路径，完成时据此还原目录树
            rows.append(ProjectPhoto(
                project_id=0,  # 占位，create 后回填
                workspace_path=dest, original_path=src,
                original_rel_path=rel, filename=Path(src).name,
                capture_time=t, location=loc,
            ))

        project = self._projects.create(Project(
            name=name, source_folder=source_folder,
            workspace_dir=workspace_dir, target_dir=target_dir,
            status=ProjectStatus.GROUPING.value, photo_count=len(rows),
            time_start=min(times) if times else None,
            time_end=max(times) if times else None,
            location=self._most_common(locations),
        ))
        for r in rows:
            r.project_id = project.id
        self._photos.bulk_create(rows)
        return ProjectView.model_validate(project)

    # ── 分组 ────────────────────────────────────────────────────────────────

    def group(self, project_id: int) -> ProjectDetailResponse:
        """对 workspace 照片分组并持久化；已分组则直接返回详情（不重复分组）。"""
        project = self._require_project(project_id)
        if project.status != ProjectStatus.GROUPING.value:
            return self.get_detail(project_id)

        photos = self._photos.by_project(project_id)
        by_path = {p.workspace_path: p for p in photos}
        resp = self._grouping.group(GroupRequest(photos=list(by_path.keys())))

        changed: list[ProjectPhoto] = []
        group_rows: list[PhotoGroup] = []
        for g in resp.groups:
            members = [by_path[p] for p in g.photos if p in by_path]
            for ph in members:
                ph.group_key = g.id
                changed.append(ph)
            times = [m.capture_time for m in members if m.capture_time]
            group_rows.append(PhotoGroup(
                project_id=project_id, group_key=g.id,
                location=self._most_common([m.location for m in members if m.location]),
                time_start=min(times) if times else None,
                time_end=max(times) if times else None,
                status=GroupStatus.PENDING.value,
            ))
        if changed:
            self._photos.update_many(changed)
        if group_rows:
            self._groups.bulk_create(group_rows)

        project.status = ProjectStatus.SELECTING.value
        self._projects.update(project)
        return self.get_detail(project_id)

    # ── 评测（层①+层②）──────────────────────────────────────────────────────

    # ── 评测核心：首评 / 重试 共用 ───────────────────────────────────────────

    @staticmethod
    def _mark_l1_ok(p: ProjectPhoto, ls) -> None:
        p.local_score = ls.score
        p.local_detail = ls.detail.model_dump() if ls.detail else None
        p.assess_status = AssessStatus.SUCCESS.value
        p.assess_error = None
        p.assess_error_ignored = False

    @staticmethod
    def _mark_l2_ok(p: ProjectPhoto, sc) -> None:
        p.llm_score = sc.score
        p.llm_reason = sc.reason
        p.llm_flaws = sc.flaws
        p.llm_editable = sc.editable
        p.llm_edit_advice = sc.edit_advice
        p.assess_status = AssessStatus.SUCCESS.value
        p.assess_error = None
        p.assess_error_ignored = False

    @staticmethod
    def _mark_failed(p: ProjectPhoto, status: AssessStatus, error: str) -> None:
        p.assess_status = status.value
        p.assess_error = error

    def _assess_and_rank(
        self, group: PhotoGroup, photos: list[ProjectPhoto],
        targets: list[ProjectPhoto] | None = None,
        *, group_index: int = 1, group_count: int = 1,
    ) -> None:
        """统一评测内核：对缺分/失败且在 targets 内的图调模型，按全组最新分（失败按 0）
        重算 survivors/kept/selection。targets=None 表示全组（首评）。"""
        by_path = {p.workspace_path: p for p in photos}
        target_set = set(by_path) if targets is None else {p.workspace_path for p in targets}

        # 层①：首评(NOT_ASSESSED) 全跑 + 重试目标里的层①失败
        need_l1 = [
            p for p in photos
            if p.assess_status == AssessStatus.NOT_ASSESSED.value
            or (p.assess_status == AssessStatus.LAYER1_FAILED.value and p.workspace_path in target_set)
        ]

        pid = group.project_id
        tick: Callable[[], None] = lambda: self._progress.tick(pid)  # noqa: E731 —— 局部进度回调
        self._progress.begin(
            pid, group.group_key, group_index, group_count,
            phase=AssessPhase.LAYER1, total=len(need_l1),
        )

        if need_l1:
            resp1 = self._assess.assess(AssessRequest(
                group_id=group.group_key,
                photos=[PhotoRef(path=p.workspace_path) for p in need_l1],
            ), on_progress=tick)
            for ls in resp1.scores:
                if (p := by_path.get(ls.path)):
                    self._mark_l1_ok(p, ls)
            for err in resp1.errors:
                if (p := by_path.get(err.path)):
                    self._mark_failed(p, AssessStatus.LAYER1_FAILED, err.error)
        self._photos.update_many(photos)  # 先落层①，层②失败不白跑

        # 重算 survivors（全组，失败/无分按 0；失败图按 0 分照常参与漏斗，不做特例排除）
        total = len(photos)
        m = self._params.compute_m(self._params.compute_n(total))
        local_scored = [LocalScore(path=p.workspace_path, score=p.local_score or 0.0) for p in photos]
        survivor_paths = {ls.path for ls, _ in self._funnel.apply_funnel(local_scored, m)}
        survivors = [p for p in photos if p.workspace_path in survivor_paths]

        # 层②：survivor 里需打分（新晋/首次 SUCCESS 无 llm 分 + 目标里的层②失败）；层①失败者不调
        need_l2 = [
            p for p in survivors
            if p.llm_score is None and (
                p.assess_status == AssessStatus.SUCCESS.value
                or (p.assess_status == AssessStatus.LAYER2_FAILED.value and p.workspace_path in target_set)
            )
        ]

        self._progress.phase(pid, AssessPhase.LAYER2, total=len(need_l2))

        if need_l2:
            resp2 = self._scoring.score(ScoreRequest(
                group_id=group.group_key,
                photos=[p.workspace_path for p in need_l2],
                group_total=total,
            ), on_progress=tick)
            for sc in resp2.scores:
                if (p := by_path.get(sc.path)):
                    self._mark_l2_ok(p, sc)
            for err in resp2.errors:
                if (p := by_path.get(err.path)):
                    self._mark_failed(p, AssessStatus.LAYER2_FAILED, err.error)

        # 重算 kept（全组 survivors，缺分/失败按 0 照常参与排名，不做特例排除）
        n = self._params.compute_n(total)
        llm_scored = [
            Score(path=p.workspace_path, score=p.llm_score or 0.0,
                  reason=p.llm_reason or "", flaws=p.llm_flaws or "")
            for p in survivors
        ]
        pk_set = self._ranking.assemble_pk_set(group.group_key, llm_scored, n)
        kept_paths = {e.path for e in pk_set.entries}
        origin_by_path = {e.path: e.origin.value for e in pk_set.entries}

        for p in photos:
            if p.workspace_path in kept_paths:
                p.selection = Selection.KEPT.value
                p.origin = origin_by_path.get(p.workspace_path)
            else:
                p.selection = Selection.DISCARDED.value
                p.origin = None
        self._photos.update_many(photos)

        group.status = GroupStatus.ASSESSED.value
        self._groups.update(group)

    def _assess_one(
        self, project_id: int, group: PhotoGroup, group_index: int, group_count: int
    ) -> None:
        """评测单组（含空组兜底）；复用评测内核。不收尾 done()，由调用方统一收尾。"""
        photos = self._photos.by_group(project_id, group.group_key)
        if not photos:
            group.status = GroupStatus.ASSESSED.value
            self._groups.update(group)
            return
        self._assess_and_rank(group, photos, group_index=group_index, group_count=group_count)

    def assess_group(self, project_id: int, group_key: str) -> GroupDetailResponse:
        """对一组跑层①+层②并持久化、初始化去留；已评测则原样返回（不覆盖用户裁决）。"""
        group = self._require_group(project_id, group_key)
        if group.status != GroupStatus.PENDING.value:
            return self.get_group_detail(project_id, group_key)
        try:
            self._assess_one(project_id, group, group_index=1, group_count=1)
        finally:
            self._progress.done(project_id)
        return self.get_group_detail(project_id, group_key)

    def retry_group(
        self, project_id: int, group_key: str, photo_id: int | None = None
    ) -> GroupDetailResponse:
        """重评失败图（单张 / 该组全部未解决失败），再按全组最新分重算去留。"""
        group = self._require_group(project_id, group_key)
        photos = self._photos.by_group(project_id, group_key)
        failed = {
            AssessStatus.LAYER1_FAILED.value, AssessStatus.LAYER2_FAILED.value
        }
        if photo_id is not None:
            targets = [p for p in photos if p.id == photo_id and p.assess_status in failed and not p.assess_error_ignored]
        else:
            targets = [p for p in photos if p.assess_status in failed and not p.assess_error_ignored]
        if targets:
            try:
                self._assess_and_rank(group, photos, targets=targets, group_index=1, group_count=1)
            finally:
                self._progress.done(project_id)
        return self.get_group_detail(project_id, group_key)

    def ignore_failures(
        self, project_id: int, group_key: str, photo_id: int | None = None
    ) -> GroupDetailResponse:
        """把失败图标记为已忽略（解阻塞），不重评、不重算去留。"""
        self._require_group(project_id, group_key)
        photos = self._photos.by_group(project_id, group_key)
        failed = {
            AssessStatus.LAYER1_FAILED.value, AssessStatus.LAYER2_FAILED.value
        }
        touched = [
            p for p in photos
            if p.assess_status in failed and (photo_id is None or p.id == photo_id)
        ]
        for p in touched:
            p.assess_error_ignored = True
        if touched:
            self._photos.update_many(touched)
        return self.get_group_detail(project_id, group_key)

    # ── 用户裁决 ──────────────────────────────────────────────────────────────

    def update_selection(
        self, project_id: int, group_key: str, changes: list[SelectionChange]
    ) -> GroupDetailResponse:
        """手动改去留 / 标记救回。"""
        self._require_no_unresolved_failures(project_id, group_key)
        photos = self._photos.by_group(project_id, group_key)
        by_id = {p.id: p for p in photos}
        touched: list[ProjectPhoto] = []
        for c in changes:
            p = by_id.get(c.photo_id)
            if not p:
                continue
            if c.selection is not None:
                p.selection = c.selection.value
            if c.rescued is not None:
                p.rescued = c.rescued
            touched.append(p)
        if touched:
            self._photos.update_many(touched)
        return self.get_group_detail(project_id, group_key)

    def confirm_group(self, project_id: int, group_key: str) -> GroupDetailResponse:
        """确认本组（标识，可反复改回）。"""
        group = self._require_group(project_id, group_key)
        self._require_no_unresolved_failures(project_id, group_key)
        group.status = GroupStatus.CONFIRMED.value
        self._groups.update(group)
        return self.get_group_detail(project_id, group_key)

    def confirm_all(self, project_id: int) -> ProjectDetailResponse:
        """一键通过：未评测的组先评测（默认信任大模型），再把所有组置为已确认。

        跨组「不」并行：组内层①已逐张并发、层②已按 ark_concurrency 并发；若再跨组并行，
        会叠加放大本地模型与显存/CPU 占用，风险（OOM/抖动）大于收益，故此处逐组串行。
        """
        self._require_project(project_id)
        pending = [g for g in self._groups.by_project(project_id)
                   if g.status == GroupStatus.PENDING.value]
        try:
            for idx, g in enumerate(pending, start=1):
                self._assess_one(project_id, g, group_index=idx, group_count=len(pending))
        finally:
            self._progress.done(project_id)
        for g in self._groups.by_project(project_id):
            self._require_no_unresolved_failures(project_id, g.group_key)
        for g in self._groups.by_project(project_id):
            if g.status != GroupStatus.CONFIRMED.value:
                g.status = GroupStatus.CONFIRMED.value
                self._groups.update(g)
        return self.get_detail(project_id)

    def get_progress(self, project_id: int) -> AssessProgress:
        """读当前评测进度（纯读内存、不查 DB）；未知/空闲项目返回 IDLE 默认。

        刻意不设 PROJECT_NOT_FOUND 门禁：进度是高频轮询的只读侧信道，
        避开 DB 既免锁竞争又更快；未知项目返回 IDLE 即可。
        """
        return self._progress.get(project_id)

    # ── 完成 ────────────────────────────────────────────────────────────────

    def complete(self, project_id: int) -> CompleteResponse:
        """门禁=全组已确认；复制「通过」到目标目录 → 删 workspace → 标记完成。"""
        project = self._require_project(project_id)
        groups = self._groups.by_project(project_id)
        if not groups or any(g.status != GroupStatus.CONFIRMED.value for g in groups):
            raise BizException(BizCode.GROUPS_NOT_ALL_CONFIRMED)

        kept = self._photos.kept_of(project_id)
        # 按相对路径还原原始目录树 + 原始文件名（rel 为空的老数据兜底拍平到原名）
        items = [(p.workspace_path, p.original_rel_path or p.filename) for p in kept]
        self._workspace.restore_tree(items, project.target_dir)
        self._workspace.remove_dir(project.workspace_dir)
        project.status = ProjectStatus.COMPLETED.value
        project.completed_at = datetime.now()
        self._projects.update(project)
        return CompleteResponse(output_dir=project.target_dir, kept_count=len(kept))

    # ── 删除 ────────────────────────────────────────────────────────────────

    def delete(self, project_id: int) -> None:
        """删除项目：清掉 workspace 副本目录 + 全部数据库资源（照片/组/PK/项目行）。

        只删副本与项目自身存档，绝不动源文件夹与已完成项目的输出目录。
        """
        project = self._require_project(project_id)
        self._workspace.remove_dir(project.workspace_dir)  # best-effort；已完成的项目副本可能已清
        self._pk_states.delete_by_project(project_id)
        self._photos.delete_by_project(project_id)
        self._groups.delete_by_project(project_id)
        self._projects.delete(project_id)

    # ── 读取 ────────────────────────────────────────────────────────────────

    def list_projects(self) -> list[ProjectView]:
        return [ProjectView.model_validate(p) for p in self._projects.all()]

    def get_detail(self, project_id: int) -> ProjectDetailResponse:
        project = self._require_project(project_id)
        photos = self._photos.by_project(project_id)
        summaries = [
            self._summarize(g, [p for p in photos if p.group_key == g.group_key])
            for g in self._groups.by_project(project_id)
        ]
        return ProjectDetailResponse(project=ProjectView.model_validate(project), groups=summaries)

    def get_group_detail(self, project_id: int, group_key: str) -> GroupDetailResponse:
        group = self._require_group(project_id, group_key)
        photos = self._photos.by_group(project_id, group_key)
        return GroupDetailResponse(
            project_id=project_id,
            group=self._summarize(group, photos),
            photos=[PhotoView.model_validate(p) for p in photos],
            pk=self._pk.get_view(project_id, group_key),
        )

    # ── 内部工具 ──────────────────────────────────────────────────────────────

    def _extract(self, path: str) -> tuple[datetime | None, str | None, str | None]:
        """读单张的拍摄时间 + 拍摄地名（坐标反查）；失败返回错误串，不抛。"""
        try:
            img = self._open_for_exif(path)
            t = imaging.read_capture_time(img)
            gps = imaging.read_gps(img)
            loc = self._geocode.reverse(*gps) if gps else None
            return t, loc, None
        except Exception as e:  # noqa: BLE001 —— 单张元数据失败上报、不中断
            return None, None, f"{type(e).__name__}: {e}"

    @staticmethod
    def _open_for_exif(path: str) -> Image.Image:
        """为读 EXIF 打开图：普通图懒加载只读头；RAW 走内嵌预览。"""
        if Path(path).suffix.lower() in imaging.IMAGE_EXTS:
            return Image.open(path)
        return imaging.load_for_analysis(path)

    @staticmethod
    def _most_common(values: list[str]) -> str | None:
        return Counter(values).most_common(1)[0][0] if values else None

    @staticmethod
    def _summarize(group: PhotoGroup, photos: list[ProjectPhoto]) -> GroupSummary:
        return GroupSummary(
            group_key=group.group_key, location=group.location,
            time_start=group.time_start, time_end=group.time_end, status=group.status,
            photo_count=len(photos),
            kept_count=sum(1 for p in photos if p.selection == Selection.KEPT.value),
            failed_count=sum(
                1 for p in photos
                if p.assess_status in (AssessStatus.LAYER1_FAILED.value, AssessStatus.LAYER2_FAILED.value) and not p.assess_error_ignored
            ),
            photo_paths=[p.workspace_path for p in photos],
            photo_names=[p.original_rel_path or p.filename for p in photos],
        )

    @staticmethod
    def _validate_name(name: str) -> str:
        name = (name or "").strip()
        if not name:
            raise BizException(BizCode.INVALID_PROJECT_NAME, "项目名不能为空")
        if any(sep in name for sep in ("/", "\\")) or name in (".", "..") or "\x00" in name:
            raise BizException(BizCode.INVALID_PROJECT_NAME, "项目名不能包含路径分隔符")
        return name

    def _require_project(self, project_id: int) -> Project:
        project = self._projects.get(project_id)
        if not project:
            raise BizException(BizCode.PROJECT_NOT_FOUND, f"项目不存在：{project_id}")
        return project

    def _require_group(self, project_id: int, group_key: str) -> PhotoGroup:
        group = self._groups.get(project_id, group_key)
        if not group:
            raise BizException(BizCode.GROUP_NOT_FOUND, f"分组不存在：{group_key}")
        return group

    def _require_no_unresolved_failures(self, project_id: int, group_key: str) -> None:
        if self._photos.unresolved_failures(project_id, group_key):
            raise BizException(BizCode.GROUP_HAS_UNRESOLVED_FAILURES)
