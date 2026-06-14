"""FastAPI app 工厂：建容器 → wire（由容器 wiring_config 自动完成）→ CORS → lifespan → 注册路由。

只监听 127.0.0.1，由 Tauri 壳经 localhost 调用。
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .container import Container
from .controller import (
    assess_controller,
    group_controller,
    health_controller,
    score_controller,
    thumbnail_controller,
)


def create_app() -> FastAPI:
    """构建并返回 FastAPI 应用（容器挂在 app.container 上，便于测试 override）。"""
    container = Container()
    settings = container.settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 后台预热，不阻塞启动；启动后立刻可应答 /health（报 loading），就绪后转 ready。
        container.readiness_service().start_warmup()
        yield

    app = FastAPI(title="Keeper Engine", version=__version__, lifespan=lifespan)
    app.container = container

    # 桌面端 Tauri webview 经浏览器上下文跨源调用本服务，需放行本地来源。
    # 服务只绑 127.0.0.1（仅本机可达），故放行 localhost / tauri 来源是安全的。
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=settings.cors_origin_regex,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for module in (
        health_controller,
        thumbnail_controller,
        group_controller,
        assess_controller,
        score_controller,
    ):
        app.include_router(module.router)

    return app
