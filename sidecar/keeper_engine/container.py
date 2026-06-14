"""依赖注入容器：装配全部 provider，controller 经 wiring 注入 service。

分层依赖在这里一处装配：
  settings → client（vision/scorer）→ service → controller。
Scorer 的绑定是全系统唯一会演化的点——商业版换 CloudRelayScorer 只改 `scorer` 这一行，
业务流程（service/controller）一律不动（CLAUDE.md：Scorer 可替换）。
"""

from __future__ import annotations

from dependency_injector import containers, providers

from .client.scorer import LocalDirectScorer
from .client.vision_client import VisionClient
from .config.settings import Settings
from .service.assess_service import AssessService
from .service.funnel_service import FunnelService
from .service.grouping_service import GroupingService
from .service.params_service import ParamsService
from .service.prescreen_service import PrescreenService
from .service.ranking_service import RankingService
from .service.readiness_service import ReadinessService
from .service.scoring_service import ScoringService


class Container(containers.DeclarativeContainer):
    """声明式 DI 容器。controller 包内的 @inject 自动按此装配。"""

    wiring_config = containers.WiringConfiguration(packages=["keeper_engine.controller"])

    settings = providers.Singleton(Settings)

    # ── 外部依赖客户端（有状态/有外部连接，单例）──
    vision_client = providers.Singleton(VisionClient, settings=settings)
    scorer = providers.Singleton(LocalDirectScorer, settings=settings)  # ← 切 CloudRelayScorer 只改这行

    # ── 就绪态：全局共享，单例 ──
    readiness_service = providers.Singleton(ReadinessService, vision=vision_client, settings=settings)

    # ── 无状态领域服务 ──
    funnel_service = providers.Factory(FunnelService)
    params_service = providers.Factory(ParamsService)
    ranking_service = providers.Factory(RankingService, funnel=funnel_service)

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
    )
    scoring_service = providers.Factory(
        ScoringService,
        scorer=scorer,
        params=params_service,
        ranking=ranking_service,
        settings=settings,
    )
