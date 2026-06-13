"""层① 评分合成的测试——mock 掉模型（vision.*），只验证合成与 reason 逻辑。"""

import numpy as np
import pytest
from PIL import Image

from keeper_engine import prescreen, vision


@pytest.fixture
def noise_image(tmp_path):
    """高频随机噪声图：锐度高、熵高、亮度居中——无任何扣分项。"""
    arr = np.random.default_rng(0).integers(0, 255, (200, 200, 3), dtype=np.uint8)
    p = tmp_path / "noise.png"
    Image.fromarray(arr).save(p)
    return str(p)


@pytest.fixture
def dark_image(tmp_path):
    arr = np.full((200, 200, 3), 5, dtype=np.uint8)
    p = tmp_path / "dark.png"
    Image.fromarray(arr).save(p)
    return str(p)


def _mock_iqa(monkeypatch, topiq=0.8, clipiqa=0.7):
    monkeypatch.setattr(vision, "topiq_score", lambda img: topiq)
    monkeypatch.setattr(vision, "topiq_face_score", lambda img: topiq)  # 有脸时走这个
    monkeypatch.setattr(vision, "clipiqa_plus_score", lambda img: clipiqa)


def test_clean_image_high_score_no_reason(monkeypatch, noise_image):
    monkeypatch.setattr(vision, "extract_faces", lambda img: [])
    _mock_iqa(monkeypatch)
    ls = prescreen.assess_photo(noise_image)
    assert ls.path == noise_image
    assert ls.score > 50.0
    assert ls.reason == ""


def test_dark_image_flagged_underexposed(monkeypatch, dark_image):
    monkeypatch.setattr(vision, "extract_faces", lambda img: [])
    _mock_iqa(monkeypatch)
    ls = prescreen.assess_photo(dark_image)
    assert ls.reason == "欠曝"
    assert ls.score < 80.0


def test_face_iqa_falls_back_when_no_face_detected(monkeypatch, noise_image):
    """topiq_nr-face 内部检不到脸抛 AssertionError 时，回退通用 topiq_nr，不崩、不丢图。"""
    face = {"bbox": (50, 50, 150, 150), "det_score": 0.9,
            "embedding": None, "kps": None, "landmark_2d_68": None}
    monkeypatch.setattr(vision, "extract_faces", lambda img: [face])
    monkeypatch.setattr(vision, "eye_open_score", lambda f: 0.3)  # 睁眼
    monkeypatch.setattr(vision, "topiq_face_score",
                        lambda img: (_ for _ in ()).throw(AssertionError("No face detected")))
    monkeypatch.setattr(vision, "topiq_score", lambda img: 0.9)   # 回退目标
    monkeypatch.setattr(vision, "clipiqa_plus_score", lambda img: 0.7)
    ls = prescreen.assess_photo(noise_image)
    assert ls.score > 0.0  # 成功回退、正常打分，未抛异常


def test_closed_eyes_flagged(monkeypatch, noise_image):
    face = {
        "bbox": (50, 50, 150, 150), "det_score": 0.9,
        "embedding": np.ones(512, np.float32), "kps": None, "landmark_2d_68": None,
    }
    monkeypatch.setattr(vision, "extract_faces", lambda img: [face])
    monkeypatch.setattr(vision, "eye_open_score", lambda f: 0.1)  # 闭眼
    _mock_iqa(monkeypatch)
    ls = prescreen.assess_photo(noise_image)
    assert ls.reason == "闭眼"
