"""ProgressTracker 纯内存进度侧信道测试：阶段切换、tick 计数、空闲默认、隔离副本。"""

import threading

from keeper_engine.enumeration.assess_phase import AssessPhase
from keeper_engine.service.progress_tracker import ProgressTracker


def test_idle_when_unknown_project():
    t = ProgressTracker()
    p = t.get(99)
    assert p.phase == AssessPhase.IDLE.value
    assert (p.done, p.total, p.group_index, p.group_count, p.group_key) == (0, 0, 0, 0, None)


def test_begin_phase_tick_done_flow():
    t = ProgressTracker()
    t.begin(1, "g1", group_index=2, group_count=5, phase=AssessPhase.LAYER1, total=3)
    p = t.get(1)
    assert (p.phase, p.done, p.total, p.group_index, p.group_count, p.group_key) == (
        "LAYER1", 0, 3, 2, 5, "g1",
    )
    t.tick(1)
    t.tick(1)
    assert t.get(1).done == 2
    t.phase(1, AssessPhase.LAYER2, total=4)  # 切阶段重置 done
    assert (t.get(1).phase, t.get(1).done, t.get(1).total) == ("LAYER2", 0, 4)
    t.done(1)
    assert t.get(1).phase == "DONE"


def test_get_returns_isolated_copy():
    t = ProgressTracker()
    t.begin(1, "g1", 1, 1, AssessPhase.LAYER1, total=2)
    snap = t.get(1)
    t.tick(1)
    assert snap.done == 0  # 旧快照不受后续 tick 影响


def test_tick_is_thread_safe():
    t = ProgressTracker()
    t.begin(1, "g1", 1, 1, AssessPhase.LAYER1, total=1000)
    def worker():
        for _ in range(100):
            t.tick(1)
    threads = [threading.Thread(target=worker) for _ in range(10)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert t.get(1).done == 1000


def test_phase_tick_done_noop_when_no_record():
    t = ProgressTracker()
    t.phase(1, AssessPhase.LAYER2, 3)  # 不抛
    t.tick(1)
    t.done(1)
    assert t.get(1).phase == AssessPhase.IDLE.value
