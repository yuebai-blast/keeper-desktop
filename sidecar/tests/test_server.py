"""/assess 端点接线的测试——mock 掉 prescreen.assess_photo，验证 N/M + 漏斗 + 容错。"""

import pytest

from keeper_engine import prescreen, server
from keeper_engine.models import AssessRequest, LocalScore, PhotoRef


def _req(*paths):
    return AssessRequest(group_id="g1", photos=[PhotoRef(path=p) for p in paths])


@pytest.fixture(autouse=True)
def _ready(monkeypatch):
    """这些端点测试默认模型已就绪（绕过预热）；测就绪门禁的用例自行覆盖。"""
    monkeypatch.setattr(server._readiness, "status", "ready")


def test_assess_503_when_models_not_ready(monkeypatch):
    from fastapi import HTTPException
    monkeypatch.setattr(server._readiness, "status", "loading")
    with pytest.raises(HTTPException) as ei:
        server.assess(_req("p0"))
    assert ei.value.status_code == 503


def test_assess_wires_funnel_and_params(monkeypatch):
    # 10 张，分数从高到低；>=60 的有 6 张
    scores = dict(zip(
        [f"p{i}" for i in range(10)],
        [95, 90, 85, 80, 75, 70, 55, 40, 30, 20],
    ))
    monkeypatch.setattr(prescreen, "assess_photo",
                        lambda path, companions=(): LocalScore(path=path, score=scores[path]))

    resp = server.assess(_req(*scores))
    assert resp.n == 3 and resp.m == 5            # N=max(2,3)=3, M=ceil(4.5)=5
    # 达标 6 张 > M(5) → 6 张全过，按分降序，且都标 passed（分≥60）
    assert [s.path for s in resp.survivors] == ["p0", "p1", "p2", "p3", "p4", "p5"]
    assert all(s.origin == "passed" for s in resp.survivors)
    assert resp.errors == []


def test_assess_records_per_photo_errors(monkeypatch):
    def fake(path, companions=()):
        if path == "bad":
            raise ValueError("文件损坏")
        return LocalScore(path=path, score=90)

    monkeypatch.setattr(prescreen, "assess_photo", fake)
    resp = server.assess(_req("good1", "bad", "good2"))
    assert [s.path for s in resp.scores] == ["good1", "good2"]
    assert len(resp.errors) == 1 and resp.errors[0].path == "bad"
    assert "文件损坏" in resp.errors[0].error


def test_assess_model_unavailable_raises_503(monkeypatch):
    from fastapi import HTTPException

    from keeper_engine.vision import VisionUnavailable

    def boom(path, companions=()):
        raise VisionUnavailable("权重缺失")

    monkeypatch.setattr(prescreen, "assess_photo", boom)
    with pytest.raises(HTTPException) as ei:
        server.assess(_req("p0"))
    assert ei.value.status_code == 503
