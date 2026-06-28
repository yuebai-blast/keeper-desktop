"""分组聚类 GroupingService.cluster() 的测试——合成归一特征 + 时间，纯函数、无模型。"""

from datetime import datetime, timedelta

import numpy as np

from keeper_engine.request.group_request import GroupRequest
from keeper_engine.service.grouping_service import GroupingService


def _unit(*v) -> np.ndarray:
    a = np.array(v, dtype=np.float32)
    return a / np.linalg.norm(a)


def _faces(*vecs) -> np.ndarray:
    """把若干已归一人脸向量堆叠成 (k×d) 人脸集合。"""
    return np.stack(vecs)


T0 = datetime(2024, 1, 1, 12, 0, 0)


def test_empty_and_single():
    assert GroupingService.cluster([], [], []) == []
    g = GroupingService.cluster(["a"], [_unit(1, 0, 0)], [T0])
    assert len(g) == 1 and g[0].photos == ["a"]


def test_two_semantic_clusters_same_time():
    """语义分两簇、时间相同 → 分成两组。"""
    embs = [_unit(1, 0, 0), _unit(1, 0, 0), _unit(0, 1, 0), _unit(0, 1, 0)]
    groups = GroupingService.cluster(["a1", "a2", "b1", "b2"], embs, [T0] * 4)
    assert len(groups) == 2
    photos = {frozenset(g.photos) for g in groups}
    assert photos == {frozenset({"a1", "a2"}), frozenset({"b1", "b2"})}
    assert [g.id for g in groups] == ["g1", "g2"]  # 按首次出现编号


def test_same_scene_split_by_time_gap():
    """画面几乎相同，但时间隔了 1 小时 → 时间衰减把它们拆成两组。"""
    embs = [_unit(1, 0, 0)] * 4
    times = [T0, T0 + timedelta(seconds=1), T0 + timedelta(hours=1), T0 + timedelta(hours=1, seconds=1)]
    groups = GroupingService.cluster(["x1", "x2", "y1", "y2"], embs, times)
    assert len(groups) == 2
    photos = {frozenset(g.photos) for g in groups}
    assert photos == {frozenset({"x1", "x2"}), frozenset({"y1", "y2"})}


def test_missing_time_falls_back_to_semantics():
    """无 EXIF 时间（None）→ 不做时间衰减，纯靠语义：相同画面归一组。"""
    embs = [_unit(1, 0, 0), _unit(1, 0, 0)]
    groups = GroupingService.cluster(["a", "b"], embs, [None, None])
    assert len(groups) == 1 and set(groups[0].photos) == {"a", "b"}


def test_same_scene_different_people_split():
    """画面相同、时间相同，但人脸身份不同 → 人脸因子把不同人拆成两组。"""
    embs = [_unit(1, 0, 0)] * 4
    p1, p2 = _unit(1, 0, 0, 0), _unit(0, 1, 0, 0)
    faces = [_faces(p1), _faces(p1), _faces(p2), _faces(p2)]
    groups = GroupingService.cluster(["a1", "a2", "b1", "b2"], embs, [T0] * 4, faces)
    assert len(groups) == 2
    photos = {frozenset(g.photos) for g in groups}
    assert photos == {frozenset({"a1", "a2"}), frozenset({"b1", "b2"})}


def test_same_scene_same_person_one_group():
    """画面相同、时间相同、同一个人 → 人脸因子≈1，不干预，仍归一组。"""
    embs = [_unit(1, 0, 0)] * 2
    p1 = _unit(1, 0, 0, 0)
    groups = GroupingService.cluster(["a", "b"], embs, [T0] * 2, [_faces(p1), _faces(p1)])
    assert len(groups) == 1 and set(groups[0].photos) == {"a", "b"}


def test_group_photo_same_people_one_group():
    """两张多人合影、同一拨人（同一组身份集合）→ 集合相似度高，归一组。"""
    embs = [_unit(1, 0, 0)] * 2
    p1, p2 = _unit(1, 0, 0, 0), _unit(0, 1, 0, 0)
    groups = GroupingService.cluster(["a", "b"], embs, [T0] * 2, [_faces(p1, p2), _faces(p1, p2)])
    assert len(groups) == 1 and set(groups[0].photos) == {"a", "b"}


def test_group_photo_different_people_split():
    """两张合影人群完全不同（无重叠）→ 集合相似度≈0，拆成两组。"""
    embs = [_unit(1, 0, 0)] * 2
    p1, p2 = _unit(1, 0, 0, 0), _unit(0, 1, 0, 0)
    p3, p4 = _unit(0, 0, 1, 0), _unit(0, 0, 0, 1)
    groups = GroupingService.cluster(["a", "b"], embs, [T0] * 2, [_faces(p1, p2), _faces(p3, p4)])
    assert len(groups) == 2


def test_face_missing_does_not_penalize():
    """任一张无脸（None）→ 人脸因子=1，不惩罚相似度，退回纯语义+时间（同场景归一组）。"""
    embs = [_unit(1, 0, 0)] * 2
    groups = GroupingService.cluster(["a", "b"], embs, [T0] * 2, [None, _faces(_unit(0, 1, 0, 0))])
    assert len(groups) == 1 and set(groups[0].photos) == {"a", "b"}


class _ReadyReadiness:
    status = "ready"
    detail = ""


def _grouping_service():
    # vision 不会被用到——下面 monkeypatch 掉 embed_photo
    return GroupingService(vision=object(), readiness=_ReadyReadiness())


def test_group_ticks_on_progress_per_photo_and_on_cluster_once(monkeypatch):
    svc = _grouping_service()
    monkeypatch.setattr(svc, "embed_photo", lambda p, companions=(): (_unit(1, 0, 0), None, T0))
    ticks, clusters = [], []
    svc.group(
        GroupRequest(photos=["a", "b", "c"]),
        on_progress=lambda: ticks.append(1),
        on_cluster=lambda: clusters.append(1),
    )
    assert len(ticks) == 3      # 每张一次
    assert len(clusters) == 1   # 切聚类一次


def test_group_ticks_even_for_failed_photo(monkeypatch):
    svc = _grouping_service()

    def fake_embed(p, companions=()):
        if p == "b":
            raise ValueError("broken file")
        return _unit(1, 0, 0), None, T0

    monkeypatch.setattr(svc, "embed_photo", fake_embed)
    ticks = []
    resp = svc.group(GroupRequest(photos=["a", "b", "c"]), on_progress=lambda: ticks.append(1))
    assert len(ticks) == 3                      # 失败图也推进度（与层①一致）
    assert [e.path for e in resp.errors] == ["b"]
