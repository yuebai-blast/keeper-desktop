"""依赖注入容器：装配全部 provider，controller 经 wiring 注入 service。

分层依赖在这里一处装配：
  settings → client（vision/scorer）→ service → controller。
Scorer 的绑定是全系统唯一会演化的点——商业版换 CloudRelayScorer 只改 `scorer` 这一行，
业务流程（service/controller）一律不动（CLAUDE.md：Scorer 可替换）。
"""

from __future__ import annotations

from dependency_injector import containers, providers

from .client.foundation_model_client import FoundationModelClient
from .client.geocode_client import GeocodeClient
from .client.scorer import LocalDirectScorer
from .client.vision_client import VisionClient
from .config.database import Database
from .config.settings import Settings
from .mapper.geocode_cache_mapper import GeocodeCacheMapper
from .mapper.model_module_mapper import ModelModuleMapper
from .mapper.photo_group_mapper import PhotoGroupMapper
from .mapper.pk_state_mapper import PkStateMapper
from .mapper.project_mapper import ProjectMapper
from .mapper.project_photo_mapper import ProjectPhotoMapper
from .service.assess_service import AssessService
from .service.funnel_service import FunnelService
from .service.grouping_service import GroupingService
from .service.params_service import ParamsService
from .service.pk_service import PkService
from .service.prescreen_service import PrescreenService
from .service.progress_tracker import ProgressTracker
from .service.project_service import ProjectService
from .service.ranking_service import RankingService
from .service.readiness_service import ReadinessService
from .service.scoring_service import ScoringService
from .service.settings_service import SettingsService
from .service.workspace_service import WorkspaceService


class Container(containers.DeclarativeContainer):
    """声明式 DI 容器。controller 包内的 @inject 自动按此装配。"""

    wiring_config = containers.WiringConfiguration(packages=["keeper_engine.controller"])

    settings = providers.Singleton(Settings)

    # ── 外部依赖客户端（有状态/有外部连接，单例）──
    vision_client = providers.Singleton(VisionClient, settings=settings)
    scorer = providers.Singleton(LocalDirectScorer, settings=settings)  # ← 切 CloudRelayScorer 只改这行
    # 管理面客户端：仅设置页「拉取视觉模型」用（AK/SK 调 ListFoundationModels），不参与打分链路
    foundation_model_client = providers.Singleton(FoundationModelClient, settings=settings)

    # ── 数据访问（sqlite，统一共享 engine）──
    database = providers.Singleton(Database, settings=settings)
    model_module_mapper = providers.Singleton(ModelModuleMapper, database=database)
    project_mapper = providers.Singleton(ProjectMapper, database=database)
    project_photo_mapper = providers.Singleton(ProjectPhotoMapper, database=database)
    photo_group_mapper = providers.Singleton(PhotoGroupMapper, database=database)
    pk_state_mapper = providers.Singleton(PkStateMapper, database=database)
    geocode_cache_mapper = providers.Singleton(GeocodeCacheMapper, database=database)

    geocode_client = providers.Singleton(GeocodeClient, settings=settings, cache=geocode_cache_mapper)

    # ── 就绪态：全局共享，单例 ──
    readiness_service = providers.Singleton(
        ReadinessService, vision=vision_client, settings=settings, mapper=model_module_mapper
    )

    # ── 评测进度：全局共享侧信道，单例 ──
    progress_tracker = providers.Singleton(ProgressTracker)

    # ── 无状态领域服务 ──
    funnel_service = providers.Factory(FunnelService)
    params_service = providers.Factory(ParamsService)
    # 设置页（自用版）：读写大模型配置。商业版构建移除此绑定与 settings_controller
    settings_service = providers.Factory(
        SettingsService, settings=settings, foundation_models=foundation_model_client
    )
    ranking_service = providers.Factory(RankingService, funnel=funnel_service)
    workspace_service = providers.Factory(WorkspaceService)

    # ── 业务编排服务 ──
    grouping_service = providers.Factory(
        GroupingService, vision=vision_client, readiness=readiness_service
    )
    prescreen_service = providers.Factory(PrescreenService, vision=vision_client)
    assess_service = providers.Factory(
        AssessService,
        prescreen=prescreen_service,
        readiness=readiness_service,
        funnel=funnel_service,
        params=params_service,
        concurrency=settings.provided.local_concurrency,
    )
    scoring_service = providers.Factory(
        ScoringService,
        scorer=scorer,
        params=params_service,
        ranking=ranking_service,
        settings=settings,
    )

    # ── 项目工作流编排（持久化 + 文件操作 + 复用上面的引擎 service）──
    pk_service = providers.Factory(
        PkService, photo_mapper=project_photo_mapper, pk_mapper=pk_state_mapper
    )
    project_service = providers.Factory(
        ProjectService,
        project_mapper=project_mapper,
        photo_mapper=project_photo_mapper,
        group_mapper=photo_group_mapper,
        pk_mapper=pk_state_mapper,
        grouping=grouping_service,
        assess=assess_service,
        scoring=scoring_service,
        pk=pk_service,
        funnel=funnel_service,
        params=params_service,
        ranking=ranking_service,
        workspace=workspace_service,
        geocode=geocode_client,
        settings=settings,
        progress=progress_tracker,
    )
