"""纯 CV 信号的测试——合成数组，无模型、确定性。"""

import numpy as np

from keeper_engine.util import signals


def _checkerboard(n=64, cell=4) -> np.ndarray:
    """高频黑白棋盘（很锐）。"""
    idx = (np.arange(n) // cell) % 2
    board = (idx[:, None] ^ idx[None, :]).astype(np.float32) * 255.0
    return board


def test_laplacian_variance_sharp_gt_blurred():
    sharp = _checkerboard()
    # 用盒式模糊把高频抹掉
    blurred = sharp.copy()
    for _ in range(3):
        blurred[1:-1, 1:-1] = (
            blurred[1:-1, 1:-1] + blurred[:-2, 1:-1] + blurred[2:, 1:-1]
            + blurred[1:-1, :-2] + blurred[1:-1, 2:]
        ) / 5.0
    assert signals.laplacian_variance(sharp) > signals.laplacian_variance(blurred)


def test_tenengrad_sharp_gt_flat():
    assert signals.tenengrad(_checkerboard()) > signals.tenengrad(np.full((64, 64), 128.0, np.float32))


def test_entropy_uniform_is_zero_random_is_high():
    uniform = np.full((64, 64), 100.0, dtype=np.float32)
    rng = np.random.default_rng(0)
    noisy = rng.uniform(0, 255, (64, 64)).astype(np.float32)
    assert signals.entropy(uniform) == 0.0
    assert signals.entropy(noisy) > 7.0


def test_exposure_signals_dark_and_bright():
    dark = np.full((32, 32), 4.0, dtype=np.float32)
    bright = np.full((32, 32), 250.0, dtype=np.float32)
    d = signals.exposure_signals(dark)
    b = signals.exposure_signals(bright)
    assert d["brightness_mean"] < 10 and d["underexposed_ratio"] == 1.0
    assert b["brightness_mean"] > 245 and b["overexposed_ratio"] == 1.0


def test_region_sharpness_with_bbox():
    board = _checkerboard()
    val = signals.region_sharpness(board, bbox=(8, 8, 56, 56))
    assert val is not None and val > 0
    # 退化 bbox（过小）返回 None
    assert signals.region_sharpness(board, bbox=(0, 0, 2, 2)) is None


def test_ear_open_vs_closed():
    open_eye = [(0, 0), (3, -2), (7, -2), (10, 0), (7, 2), (3, 2)]   # EAR=0.4
    closed_eye = [(0, 0), (3, -0.5), (7, -0.5), (10, 0), (7, 0.5), (3, 0.5)]  # EAR=0.1
    assert signals.ear(np.array(open_eye, float)) > 0.3
    assert signals.ear(np.array(closed_eye, float)) < 0.2
