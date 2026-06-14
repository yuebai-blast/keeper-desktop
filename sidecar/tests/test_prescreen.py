"""层① 评分合成的测试——注入 FakeVision 替代真实模型，只验证合成与 reason 逻辑。"""

import numpy as np
import pytest
from PIL import Image

from keeper_engine.service.prescreen_service import PrescreenService


class FakeVision:
    """桩 VisionClient：按构造参数返回固定的 IQA / 人脸信号，不加载任何模型。"""

    def __init__(self, *, faces=(), topiq=0.8, clipiqa=0.7, eye=0.3,
                 topiq_face=None, topiq_face_exc=None, topiq_face_guard=False):
        self._faces = list(faces)
        self._topiq = topiq
        self._clipiqa = clipiqa
        self._eye = eye
        self._topiq_face = topiq if topiq_face is None else topiq_face
        self._topiq_face_exc = topiq_face_exc
        self._topiq_face_guard = topiq_face_guard  # True=断言不该被调用（小脸应走回退）

    def extract_faces(self, img, **kwargs):
        return self._faces

    def topiq_score(self, img):
        return self._topiq

    def topiq_face_score(self, img):
        if self._topiq_face_guard:
            raise RuntimeError("不该被调用")
        if self._topiq_face_exc is not None:
            raise self._topiq_face_exc
        return self._topiq_face

    def clipiqa_plus_score(self, img):
        return self._clipiqa

    def eye_open_score(self, face):
        return self._eye


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


def test_clean_image_high_score_no_reason(noise_image):
    svc = PrescreenService(FakeVision(faces=[], topiq=0.8, clipiqa=0.7))
    ls = svc.assess_photo(noise_image)
    assert ls.path == noise_image
    assert ls.score > 50.0
    assert ls.primary_reason == ""


def test_dark_image_flagged_underexposed(dark_image):
    svc = PrescreenService(FakeVision(faces=[], topiq=0.8, clipiqa=0.7))
    ls = svc.assess_photo(dark_image)
    assert ls.primary_reason == "欠曝"
    assert ls.score < 80.0


def test_face_iqa_falls_back_when_no_face_detected(noise_image):
    """topiq_nr-face 内部检不到脸抛 AssertionError 时，回退通用 topiq_nr，不崩、不丢图。"""
    face = {"bbox": (50, 50, 150, 150), "det_score": 0.9,
            "embedding": None, "kps": None, "landmark_2d_68": None}
    svc = PrescreenService(FakeVision(
        faces=[face], eye=0.3, topiq=0.9, clipiqa=0.7,
        topiq_face_exc=AssertionError("No face detected"),
    ))
    ls = svc.assess_photo(noise_image)
    assert ls.score > 0.0  # 成功回退、正常打分，未抛异常


def test_small_face_falls_back_to_topiq_nr(noise_image):
    """主脸占比 < FACE_IQA_MIN_AREA(3%) 时，不用人脸IQA，回退整图 topiq_nr。"""
    # 200×200 图里 30×30 的脸 = 900/40000 = 2.25% < 3%
    face = {"bbox": (0, 0, 30, 30), "det_score": 0.9,
            "embedding": None, "kps": None, "landmark_2d_68": None}
    svc = PrescreenService(FakeVision(
        faces=[face], eye=0.3, topiq=0.7, clipiqa=0.6, topiq_face_guard=True,
    ))
    ls = svc.assess_photo(noise_image)
    assert ls.detail.tech_source == "topiq_nr"  # 走了回退，没调人脸IQA


def test_closed_eyes_flagged(noise_image):
    face = {
        "bbox": (50, 50, 150, 150), "det_score": 0.9,
        "embedding": np.ones(512, np.float32), "kps": None, "landmark_2d_68": None,
    }
    svc = PrescreenService(FakeVision(faces=[face], eye=0.1, topiq=0.8, clipiqa=0.7))
    ls = svc.assess_photo(noise_image)
    assert ls.primary_reason == "闭眼"
