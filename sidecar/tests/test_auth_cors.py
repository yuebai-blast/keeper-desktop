"""集成测试：验证 401 响应带 CORS 头。

承重行为：鉴权失败时前端必须能读到 401 状态（非网络错误）。
CORS 中间件注册在 AuthMiddleware 外层，故 401 响应也应携带 access-control-allow-origin。
若 CORS 没给 401 补头，浏览器 fetch 在跨源环境中会抛网络错（而非走 code===401 分支）。

注意：测试用 create_app() 构建完整 CORS+Auth 栈，但中间件的 token 在构建时已固化（来自
container.settings()）。因此需在构建前完成 settings override，本文件使用 monkeypatch
临时注入环境变量来绕过这个顺序约束，避免测试间污染。
"""

from fastapi.testclient import TestClient


def _make_app(tmp_path, token: str):
    """构建带完整 CORS+Auth 栈的最小 app，不触发 lifespan。

    直接按 app.py 相同中间件注册顺序（Auth 先/内层 → CORS 后/外层）组装，
    附加一个不依赖 DI 的 /ping 测试路由，验证中间件的组合行为。
    """
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    from keeper_engine.config.settings import Settings
    from keeper_engine.middleware.auth import AuthMiddleware
    from keeper_engine.response.envelope import install_exception_handlers

    s = Settings(home=tmp_path, auth_token=token)
    app = FastAPI(title="Keeper Engine Test")
    install_exception_handlers(app)
    # 与 app.py 相同注册顺序：Auth 先注册（内层）→ CORS 后注册（外层）
    app.add_middleware(AuthMiddleware, token=s.auth_token)
    app.add_middleware(
        CORSMiddleware,  # type: ignore[arg-type]
        allow_origin_regex=s.cors_origin_regex,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/ping")
    def ping():  # noqa: ANN202
        return {"ok": True}

    return app


LOCALHOST_ORIGIN = "http://localhost:1420"


def test_401_carries_cors_header(tmp_path):
    """鉴权失败（缺少 token）时响应必须带 access-control-allow-origin，前端才能读到 401。"""
    app = _make_app(tmp_path, token="secret")
    client = TestClient(app, raise_server_exceptions=False)
    # 带合法 Origin 但缺少 token，触发 401
    r = client.get("/ping", headers={"Origin": LOCALHOST_ORIGIN})
    assert r.status_code == 401
    assert "access-control-allow-origin" in r.headers, (
        "401 响应缺少 access-control-allow-origin，浏览器跨源 fetch 会报网络错而非 401"
    )


def test_401_carries_cors_header_wrong_token(tmp_path):
    """错误 token 时同样需要带 CORS 头。"""
    app = _make_app(tmp_path, token="secret")
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get(
        "/ping",
        headers={"Origin": LOCALHOST_ORIGIN, "X-Keeper-Token": "wrongtoken"},
    )
    assert r.status_code == 401
    assert "access-control-allow-origin" in r.headers


def test_correct_token_with_cors_passes(tmp_path):
    """正确 token + Origin 头：应正常返回 200，且 CORS 头存在。"""
    app = _make_app(tmp_path, token="secret")
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get(
        "/ping",
        headers={"Origin": LOCALHOST_ORIGIN, "X-Keeper-Token": "secret"},
    )
    assert r.status_code == 200
    assert "access-control-allow-origin" in r.headers
