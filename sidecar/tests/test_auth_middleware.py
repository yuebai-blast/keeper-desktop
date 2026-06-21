from fastapi import FastAPI
from fastapi.testclient import TestClient

from keeper_engine.middleware.auth import AuthMiddleware


def _client(token: str) -> TestClient:
    app = FastAPI()
    app.add_middleware(AuthMiddleware, token=token)

    @app.get("/x")
    def x():  # noqa: ANN202
        return {"ok": True}

    return TestClient(app)


def test_empty_token_passes_all():
    c = _client("")
    assert c.get("/x").status_code == 200


def test_correct_header_passes():
    c = _client("secret")
    assert c.get("/x", headers={"X-Keeper-Token": "secret"}).status_code == 200


def test_wrong_header_401():
    c = _client("secret")
    assert c.get("/x", headers={"X-Keeper-Token": "nope"}).status_code == 401


def test_missing_token_401():
    c = _client("secret")
    assert c.get("/x").status_code == 401


def test_query_token_passes():
    c = _client("secret")
    assert c.get("/x", params={"token": "secret"}).status_code == 200


def test_options_passes_without_token():
    # 中间件放行 OPTIONS（CORS 预检）；FastAPI 对仅注册了 GET 的路由返回 405（而非 401），
    # 说明中间件没有拦截它。若中间件拦截，会返回 401 PlainText 而非框架的 405。
    c = _client("secret")
    assert c.options("/x").status_code == 405
