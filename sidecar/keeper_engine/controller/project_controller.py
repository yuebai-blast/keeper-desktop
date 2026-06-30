"""项目工作流端点：新建/预览、分组、评测、裁决、PK、确认、完成。

只接线（解析请求 → 调 service → 返回），业务在 ProjectService / PkService。
就绪/大模型门禁由所复用的引擎 service 抛 BizException（MODEL_NOT_READY / SCORER_FAILED），这里不重复判断。
"""

from __future__ import annotations

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from ..container import Container
from ..request.project_request import (
    IgnoreFailuresRequest,
    MovePhotoRequest,
    PkChooseRequest,
    PkStartRequest,
    ProjectCreateRequest,
    ProjectPreviewRequest,
    RetryRequest,
    ReviewSelectionRequest,
    SelectionUpdateRequest,
)
from ..response.envelope import EnvelopeRoute
from ..response.project_response import (
    AssessProgress,
    CompleteResponse,
    GroupDetailResponse,
    PkView,
    ProjectDetailResponse,
    ProjectPreviewResponse,
    ProjectView,
    ReviewResponse,
)
from ..service.pk_service import PkService
from ..service.project_service import ProjectService

router = APIRouter(prefix="/projects", route_class=EnvelopeRoute)


@router.post("/preview", response_model=ProjectPreviewResponse)
@inject
def preview(
    req: ProjectPreviewRequest,
    svc: ProjectService = Depends(Provide[Container.project_service]),
) -> ProjectPreviewResponse:
    return svc.preview(req.folder)


@router.post("", response_model=ProjectView)
@inject
def create(
    req: ProjectCreateRequest,
    svc: ProjectService = Depends(Provide[Container.project_service]),
) -> ProjectView:
    return svc.create(req.name, req.source_folder, req.guarantee_pct, req.guarantee_fixed)


@router.get("", response_model=list[ProjectView])
@inject
def list_projects(
    svc: ProjectService = Depends(Provide[Container.project_service]),
) -> list[ProjectView]:
    return svc.list_projects()


@router.get("/{project_id}", response_model=ProjectDetailResponse)
@inject
def get_project(
    project_id: int,
    svc: ProjectService = Depends(Provide[Container.project_service]),
) -> ProjectDetailResponse:
    return svc.get_detail(project_id)


@router.delete("/{project_id}")
@inject
def delete_project(
    project_id: int,
    svc: ProjectService = Depends(Provide[Container.project_service]),
) -> None:
    """删除项目：清理 workspace 副本 + 数据库资源（项目不存在→404 语义业务码）。"""
    svc.delete(project_id)


@router.post("/{project_id}/group", response_model=ProjectDetailResponse)
@inject
def group(
    project_id: int,
    svc: ProjectService = Depends(Provide[Container.project_service]),
) -> ProjectDetailResponse:
    """分组需本地模型就绪，否则 503。"""
    return svc.group(project_id)


@router.get("/{project_id}/groups/{group_key}", response_model=GroupDetailResponse)
@inject
def get_group(
    project_id: int,
    group_key: str,
    svc: ProjectService = Depends(Provide[Container.project_service]),
) -> GroupDetailResponse:
    return svc.get_group_detail(project_id, group_key)


@router.post("/{project_id}/groups/{group_key}/assess", response_model=GroupDetailResponse)
@inject
def assess_group(
    project_id: int,
    group_key: str,
    svc: ProjectService = Depends(Provide[Container.project_service]),
) -> GroupDetailResponse:
    """层①需就绪（503）；层②缺 key/网络（502）。已评测则原样返回。"""
    return svc.assess_group(project_id, group_key)


@router.post("/{project_id}/groups/{group_key}/retry", response_model=GroupDetailResponse)
@inject
def retry_group(
    project_id: int,
    group_key: str,
    req: RetryRequest,
    svc: ProjectService = Depends(Provide[Container.project_service]),
) -> GroupDetailResponse:
    """重评失败图（层①需就绪→503；层②→502），再重算整组去留。"""
    return svc.retry_group(project_id, group_key, req.photo_id)


@router.post("/{project_id}/groups/{group_key}/ignore-failures", response_model=GroupDetailResponse)
@inject
def ignore_failures(
    project_id: int,
    group_key: str,
    req: IgnoreFailuresRequest,
    svc: ProjectService = Depends(Provide[Container.project_service]),
) -> GroupDetailResponse:
    """忽略评测失败（置 ignored，解除对本组裁决的阻塞）。"""
    return svc.ignore_failures(project_id, group_key, req.photo_id)


@router.post("/{project_id}/groups/{group_key}/selection", response_model=GroupDetailResponse)
@inject
def update_selection(
    project_id: int,
    group_key: str,
    req: SelectionUpdateRequest,
    svc: ProjectService = Depends(Provide[Container.project_service]),
) -> GroupDetailResponse:
    return svc.update_selection(project_id, group_key, req.changes)


@router.post("/{project_id}/groups/{group_key}/confirm", response_model=GroupDetailResponse)
@inject
def confirm_group(
    project_id: int,
    group_key: str,
    svc: ProjectService = Depends(Provide[Container.project_service]),
) -> GroupDetailResponse:
    return svc.confirm_group(project_id, group_key)


@router.post("/{project_id}/confirm-all", response_model=ProjectDetailResponse)
@inject
def confirm_all(
    project_id: int,
    svc: ProjectService = Depends(Provide[Container.project_service]),
) -> ProjectDetailResponse:
    """一键通过：未评测的组会触发层②大模型（可能 503/502）。"""
    return svc.confirm_all(project_id)


@router.post("/{project_id}/photos/{photo_id}/move", response_model=ProjectDetailResponse)
@inject
def move_photo(
    project_id: int,
    photo_id: int,
    req: MovePhotoRequest,
    svc: ProjectService = Depends(Provide[Container.project_service]),
) -> ProjectDetailResponse:
    """把一张照片移到目标组（只改归属）。已确认锁定/未解决失败/未评入已评 各自报业务码。"""
    return svc.move_photo(project_id, photo_id, req.target_group_key)


@router.get("/{project_id}/assess/progress", response_model=AssessProgress)
@inject
def assess_progress(
    project_id: int,
    svc: ProjectService = Depends(Provide[Container.project_service]),
) -> AssessProgress:
    """评测实时进度（高频轮询、纯读内存）；空闲/未知项目返回 IDLE。"""
    return svc.get_progress(project_id)


@router.get("/{project_id}/group/progress", response_model=AssessProgress)
@inject
def group_progress(
    project_id: int,
    svc: ProjectService = Depends(Provide[Container.project_service]),
) -> AssessProgress:
    """分组实时进度（高频轮询、纯读内存；与评测共用同一进度侧信道）。空闲/未知返回 IDLE。"""
    return svc.get_progress(project_id)


@router.post("/{project_id}/complete", response_model=CompleteResponse)
@inject
def complete(
    project_id: int,
    svc: ProjectService = Depends(Provide[Container.project_service]),
) -> CompleteResponse:
    """门禁：全组已确认，否则 400。"""
    return svc.complete(project_id)


# ── 二次预览（项目级跨组去留）────────────────────────────────────────────────

@router.get("/{project_id}/review", response_model=ReviewResponse)
@inject
def get_review(
    project_id: int,
    svc: ProjectService = Depends(Provide[Container.project_service]),
) -> ReviewResponse:
    """二次预览页：跨组拍平的 kept/discarded 去留结果。"""
    return svc.get_review(project_id)


@router.post("/{project_id}/selection", response_model=ReviewResponse)
@inject
def update_selection_batch(
    project_id: int,
    req: ReviewSelectionRequest,
    svc: ProjectService = Depends(Provide[Container.project_service]),
) -> ReviewResponse:
    """二次预览页批量改去留，返回最新分区。"""
    return svc.update_selection_batch(project_id, req.photo_ids, req.selection)


# ── PK 擂台 ──────────────────────────────────────────────────────────────────

@router.post("/{project_id}/groups/{group_key}/pk/start", response_model=PkView)
@inject
def pk_start(
    project_id: int,
    group_key: str,
    req: PkStartRequest,
    svc: PkService = Depends(Provide[Container.pk_service]),
) -> PkView:
    return svc.start(project_id, group_key, req.pool, req.restart)


@router.post("/{project_id}/groups/{group_key}/pk/choose", response_model=PkView)
@inject
def pk_choose(
    project_id: int,
    group_key: str,
    req: PkChooseRequest,
    svc: PkService = Depends(Provide[Container.pk_service]),
) -> PkView:
    return svc.choose(project_id, group_key, req.outcome)


@router.post("/{project_id}/groups/{group_key}/pk/undo", response_model=PkView)
@inject
def pk_undo(
    project_id: int,
    group_key: str,
    svc: PkService = Depends(Provide[Container.pk_service]),
) -> PkView:
    return svc.undo(project_id, group_key)
