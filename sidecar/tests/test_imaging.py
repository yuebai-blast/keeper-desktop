"""影像IO地基的测试——用临时图片，无模型。"""

import numpy as np
import pytest
from PIL import Image

from keeper_engine import imaging


def _save(tmp_path, name, arr):
    p = tmp_path / name
    Image.fromarray(arr).save(p)
    return str(p)


def test_load_for_analysis_png(tmp_path):
    rng = np.random.default_rng(0)
    arr = rng.integers(0, 255, (120, 80, 3), dtype=np.uint8)
    img = imaging.load_for_analysis(_save(tmp_path, "a.png", arr))
    assert img.mode == "RGB" and img.size == (80, 120)


def test_unsupported_ext_raises(tmp_path):
    p = tmp_path / "x.txt"
    p.write_text("nope")
    with pytest.raises(ValueError):
        imaging.load_for_analysis(str(p))


def test_to_arrays_shapes(tmp_path):
    arr = np.random.default_rng(1).integers(0, 255, (2000, 3000, 3), dtype=np.uint8)
    img = imaging.load_for_analysis(_save(tmp_path, "big.png", arr))
    gray = imaging.to_gray_array(img, max_side=768)
    rgb = imaging.to_rgb_array(img, max_side=2048)
    assert gray.dtype == np.float32 and max(gray.shape) == 768
    assert rgb.dtype == np.uint8 and rgb.shape[2] == 3 and max(rgb.shape[:2]) == 2048


def test_make_preview_under_size_limit(tmp_path):
    arr = np.random.default_rng(2).integers(0, 255, (2000, 3000, 3), dtype=np.uint8)
    img = imaging.load_for_analysis(_save(tmp_path, "big.png", arr))
    data = imaging.make_preview(img, max_side=896, max_bytes=512 * 1024)
    assert data[:2] == b"\xff\xd8"            # JPEG 魔数
    assert len(data) <= 512 * 1024
