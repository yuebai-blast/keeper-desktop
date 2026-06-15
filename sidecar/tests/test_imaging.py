"""影像IO地基的测试——用临时图片，无模型。"""

import numpy as np
import pytest
from PIL import Image

from keeper_engine.util import imaging


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


def test_cached_thumbnail_hits_cache(tmp_path, monkeypatch):
    """二次调用命中磁盘缓存——不再走生成（把 make_thumbnail 改成抛错也照样返回）。

    缓存就近落在原图同目录的 .thumbnails/{stem}@{size}.jpg。
    """
    arr = np.random.default_rng(3).integers(0, 255, (300, 400, 3), dtype=np.uint8)
    p = _save(tmp_path, "x.png", arr)

    first = imaging.cached_thumbnail(p, max_side=128)
    assert first[:2] == b"\xff\xd8"
    assert (tmp_path / ".thumbnails" / "x@128.jpg").exists()

    monkeypatch.setattr(imaging, "make_thumbnail", lambda *a, **k: (_ for _ in ()).throw(AssertionError("不该再生成")))
    second = imaging.cached_thumbnail(p, max_side=128)
    assert second == first  # 命中缓存


def test_cached_thumbnail_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        imaging.cached_thumbnail(str(tmp_path / "nope.jpg"))
