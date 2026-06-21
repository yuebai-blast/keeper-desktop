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
    project_controller,
    score_controller,
    settings_controller,
    thumbnail_controller,
)
from .middleware.auth import AuthMiddleware
from .response.envelope import install_exception_handlers


def create_app() -> FastAPI:
    """构建并返回 FastAPI 应用（容器挂在 app.container 上，便于测试 override）。"""
    container = Container()
    settings = container.settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 启动自检日志（非敏感）：确认 Tauri 注入的 env 是否到位。
        print(
            f"[boot] home={settings.home} models_dir={settings.models_dir} "
            f"auth={'on' if settings.auth_token else 'off'}",
            flush=True,
        )
        # 建全部 sqlite 表（模型状态 + 项目工作流），幂等。
        container.database().create_all()
        # 不阻塞启动；启动后立刻可应答 /health。首次需下载则停在 awaiting_consent 等用户确认，
        # 否则后台预热（报 loading → ready）。
        container.readiness_service().boot()
        yield

    app = FastAPI(title="Keeper Engine", version=__version__, lifespan=lifespan)
    app.container = container

    # 统一响应包装：领域异常 → HTTP 200 + ApiResponse（成功响应的自动包装在各 EnvelopeRoute）。
    install_exception_handlers(app)

    # 鉴权放在 CORS 之前注册 → CORS 处于最外层，能给 401 响应补上 CORS 头供前端读取。
    # token 为空（dev）时中间件整体放行。
    app.add_middleware(AuthMiddleware, token=settings.auth_token)

    # 桌面端 Tauri webview 经浏览器上下文跨源调用本服务，需放行本地来源。
    # 服务只绑 127.0.0.1（仅本机可达），故放行 localhost / tauri 来源是安全的。
    app.add_middleware(
        CORSMiddleware,  # type: ignore[arg-type]  # Starlette ParamSpec 签名导致 PyCharm 误报，运行无碍
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
        project_controller,
        settings_controller,  # 仅自用版：商业版构建移除
    ):
        app.include_router(module.router)

    return app
