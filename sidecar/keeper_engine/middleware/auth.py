"""sidecar HTTP 鉴权中间件。

token 为空（dev / 独立运行）→ 放行所有请求；非空（prod，由 Tauri 经 env 注入）→
每个请求必须带匹配 token：JSON 端点走 `X-Keeper-Token` 头，thumbnail（<img src> 带不了头）
走 `token` query 参数。CORS 预检 OPTIONS 放行。鉴权失败是网关层例外，返回纯 401（不走
ApiResponse 包装），与 thumbnail 的二进制豁免一致——全端点鉴权失败行为统一。
"""

from __future__ import annotations

import hmac

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response


class AuthMiddleware(BaseHTTPMiddleware):
    """鉴权中间件。

    注意：BaseHTTPMiddleware 会在内部缓冲整个响应体，再转交给调用方。当前所有端点均返回普通
    JSON/PlainText 响应，无 StreamingResponse，故此实现可行。若将来有端点需要返回
    StreamingResponse（如大文件流式下载），BaseHTTPMiddleware 会破坏流式语义，需改为纯
    ASGI 中间件（直接实现 `async def __call__(scope, receive, send)`）。
    """

    def __init__(self, app, token: str) -> None:  # noqa: ANN001
        super().__init__(app)
        self._token = token

    async def dispatch(self, request: Request, call_next) -> Response:  # noqa: ANN001
        if not self._token:
            return await call_next(request)
        if request.method == "OPTIONS":  # CORS 预检放行
            return await call_next(request)
        supplied = request.headers.get("x-keeper-token") or request.query_params.get("token")
        if not supplied or not hmac.compare_digest(supplied, self._token):
            return PlainTextResponse("unauthorized", status_code=401)
        return await call_next(request)
