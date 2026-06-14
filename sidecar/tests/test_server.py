"""端点接线的集成测试——TestClient + DI override / monkeypatch，不依赖真实模型或文件。

不进入 lifespan（不 `with TestClient`），故预热线程不启动；就绪态按用例需要手动置位。
"""

import pytest
from dependency_injector import providers
from fastapi.testclient import TestClient

from keeper_engine.app import create_app
from keeper_engine.exception.errors import ScorerError, VisionUnavailable
from keeper_engine.vo.local_score import LocalScore
from keeper_engine.vo.score import Score


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app)


def _ready(app):
    """把就绪态置为 ready（绕过预热）。测就绪门禁的用例不调它。"""
    app.container.readiness_service().status = "ready"


def _assess_req(*paths):
    return {"group_id": "g1", "photos": [{"path": p} for p in paths]}


class FakePrescreen:
    """桩 PrescreenService：按传入回调决定单张返回 LocalScore 还是抛错。"""

    def __init__(self, fn):
        self._fn = fn

    def assess_photo(self, path, companions=()):
        return self._fn(path)


def _override_prescreen(app, fn):
    app.container.prescreen_service.override(providers.Object(FakePrescreen(fn)))


class FakeScorer:
    """桩 Scorer：score(previews, model) 走传入回调。"""

    def __init__(self, fn):
        self._fn = fn

    def score(self, previews, model):
        return self._fn(previews, model)


def _mock_preview(monkeypatch):
    """把读图/生成预览换成桩，使 /score 测试不依赖真实文件。"""
    monkeypatch.setattr("keeper_engine.util.imaging.load_for_analysis", lambda p, *a, **k: object())
    monkeypatch.setattr("keeper_engine.util.imaging.make_preview", lambda img, **k: b"jpeg")


def test_assess_503_when_models_not_ready(client):
    # 默认就绪态 loading → 门禁拦下
    resp = client.post("/assess", json=_assess_req("p0"))
    assert resp.status_code == 503


def test_assess_wires_funnel_and_params(app, client):
    _ready(app)
    # 10 张，分数从高到低；>=60 的有 6 张
    scores = dict(zip([f"p{i}" for i in range(10)], [95, 90, 85, 80, 75, 70, 55, 40, 30, 20]))
    _override_prescreen(app, lambda p: LocalScore(path=p, score=scores[p]))

    resp = client.post("/assess", json=_assess_req(*scores))
    assert resp.status_code == 200
    body = resp.json()
    assert body["n"] == 3 and body["m"] == 5            # N=max(2,3)=3, M=ceil(4.5)=5
    # 达标 6 张 > M(5) → 6 张全过，按分降序，且都标 passed（分≥60）
    assert [s["path"] for s in body["survivors"]] == ["p0", "p1", "p2", "p3", "p4", "p5"]
    assert all(s["origin"] == "passed" for s in body["survivors"])
    assert body["errors"] == []


def test_assess_records_per_photo_errors(app, client):
    _ready(app)

    def fake(path):
        if path == "bad":
            raise ValueError("文件损坏")
        return LocalScore(path=path, score=90)

    _override_prescreen(app, fake)
    resp = client.post("/assess", json=_assess_req("good1", "bad", "good2"))
    body = resp.json()
    assert [s["path"] for s in body["scores"]] == ["good1", "good2"]
    assert len(body["errors"]) == 1 and body["errors"][0]["path"] == "bad"
    assert "文件损坏" in body["errors"][0]["error"]


def test_assess_model_unavailable_raises_503(app, client):
    _ready(app)

    def boom(path):
        raise VisionUnavailable("权重缺失")

    _override_prescreen(app, boom)
    resp = client.post("/assess", json=_assess_req("p0"))
    assert resp.status_code == 503


def test_score_wires_funnel_and_assembles_pk(app, client, monkeypatch):
    _mock_preview(monkeypatch)
    smap = {"a": 90, "b": 50}
    app.container.scorer.override(providers.Object(FakeScorer(
        lambda previews, model: [Score(path=pv.path, score=smap[pv.path]) for pv in previews]
    )))

    resp = client.post("/score", json={"group_id": "g", "photos": ["a", "b"], "group_total": 5})
    body = resp.json()
    assert body["n"] == 3  # compute_n(5) = max(ceil(1), 3)
    assert {s["path"]: s["score"] for s in body["scores"]} == {"a": 90.0, "b": 50.0}
    # K=2 <= N=3 → 两张都进 PK；a 达标 passed、b<60 兜底
    assert len(body["pk"]) == 2
    by = {e["path"]: e["origin"] for e in body["pk"]}
    assert by["a"] == "passed" and by["b"] == "quota_fill"


def test_score_502_when_scorer_unavailable(app, client, monkeypatch):
    _mock_preview(monkeypatch)

    def boom(previews, model):
        raise ScorerError("缺 key")

    app.container.scorer.override(providers.Object(FakeScorer(boom)))
    resp = client.post("/score", json={"group_id": "g", "photos": ["a"], "group_total": 3})
    assert resp.status_code == 502


def test_thumbnail_returns_jpeg(client, monkeypatch):
    monkeypatch.setattr("keeper_engine.util.imaging.cached_thumbnail", lambda p, **k: b"\xff\xd8jpeg")
    resp = client.get("/thumbnail", params={"path": "/x.jpg", "size": 256})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    assert resp.content == b"\xff\xd8jpeg"


def test_thumbnail_404_on_bad_path(client, monkeypatch):
    def boom(p, **k):
        raise FileNotFoundError("nope")

    monkeypatch.setattr("keeper_engine.util.imaging.cached_thumbnail", boom)
    resp = client.get("/thumbnail", params={"path": "/missing.jpg", "size": 256})
    assert resp.status_code == 404
