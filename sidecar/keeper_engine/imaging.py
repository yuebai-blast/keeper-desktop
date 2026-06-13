"""影像IO地基：读图、转分析数组、生成低清预览。

分组、层①、层② 都依赖它。两条产品原则在这里落地：
  - 读 RAW 只取内嵌 JPEG 预览（毫秒级、不做 demosaic），原图不改不传。
  - `make_preview` 生成的低清预览是「唯一允许上云」的产物（供层② 用，用完即焚）。
失败一律抛异常——不静默降级（CLAUDE.md）。
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

# HEIF/HEIC 支持：注册后 Image.open 即可读 .heic/.heif
try:
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:  # pillow-heif 未装时不致命，只是不支持 HEIC
    pass

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".bmp", ".tif", ".tiff"}
RAW_EXTS = {
    ".cr2", ".cr3", ".nef", ".nrw", ".arw", ".sr2", ".srf",
    ".raf", ".rw2", ".orf", ".dng", ".pef", ".raw",
}
ALL_INPUT_EXTS = IMAGE_EXTS | RAW_EXTS

# RAW 的 companion（同名伴随图）按此优先级选，越靠前画质越可靠
COMPANION_PRIORITY = [".jpg", ".jpeg", ".tif", ".tiff", ".png", ".heic", ".heif", ".webp", ".bmp"]

ANALYSIS_MAX_SIDE = 2048  # 分析用长边上限，所有本地模型/CV 共用


def load_for_analysis(path: str, companions: tuple[str, ...] | list[str] = ()) -> Image.Image:
    """加载一张用于分析的 PIL 图（已做 EXIF 方向校正、转 RGB）。

    - 普通图/HEIF：直接 Image.open。
    - RAW：① 优先用同名 companion（RAW+JPG 双拍，零解码开销）；
           ② 否则 rawpy.extract_thumb() 取内嵌 JPEG 预览。
    任何失败都抛异常，由调用方决定记录/上抛。
    """
    suffix = Path(path).suffix.lower()

    if suffix in IMAGE_EXTS:
        return _open_rgb(path)

    if suffix not in RAW_EXTS:
        raise ValueError(f"不支持的文件类型：{suffix}")

    best_comp: str | None = None
    for ext in COMPANION_PRIORITY:
        for c in companions:
            if Path(c).suffix.lower() == ext:
                best_comp = c
                break
        if best_comp:
            break
    if best_comp is not None:
        try:
            return _open_rgb(best_comp)
        except Exception:
            pass  # companion 损坏 → 退回 RAW 内嵌预览

    return _raw_embedded_preview(path)


def _open_rgb(path: str) -> Image.Image:
    img = Image.open(path)
    img.load()
    img = ImageOps.exif_transpose(img)  # 按 EXIF 方向旋正
    return img.convert("RGB")


def _raw_embedded_preview(path: str) -> Image.Image:
    try:
        import rawpy
    except ImportError as e:
        raise RuntimeError(f"无法处理 RAW {Path(path).name}：未安装 rawpy") from e

    with rawpy.imread(path) as raw:
        try:
            thumb = raw.extract_thumb()
        except (rawpy.LibRawNoThumbnailError, rawpy.LibRawUnsupportedThumbnailError) as e:
            raise RuntimeError(f"RAW {Path(path).name} 无可用内嵌预览：{e}") from e

    if thumb.format == rawpy.ThumbFormat.JPEG:
        img = Image.open(io.BytesIO(thumb.data))
        img.load()
        return ImageOps.exif_transpose(img).convert("RGB")
    if thumb.format == rawpy.ThumbFormat.BITMAP:
        return Image.fromarray(thumb.data).convert("RGB")
    raise RuntimeError(f"RAW 内嵌缩略图格式不支持：{thumb.format}")


def _resized(img: Image.Image, max_side: int) -> Image.Image:
    if max(img.size) <= max_side:
        return img
    out = img.copy()
    out.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    return out


def to_rgb_array(img: Image.Image, max_side: int = ANALYSIS_MAX_SIDE) -> np.ndarray:
    """RGB uint8 数组（H,W,3），长边限制在 max_side。"""
    return np.asarray(_resized(img.convert("RGB"), max_side), dtype=np.uint8)


def to_gray_array(img: Image.Image, max_side: int = 768) -> np.ndarray:
    """灰度 float32 数组（0–255）。锐度/曝光/熵等 CV 信号都在 768 尺度上算
    （阈值据此标定）。"""
    gray = _resized(img.convert("L"), max_side)
    arr = np.asarray(gray, dtype=np.float32)
    return arr if arr.size else np.zeros((1, 1), dtype=np.float32)


def make_preview(img: Image.Image, max_side: int = 896, max_bytes: int = 512 * 1024) -> bytes:
    """生成低清 JPEG 预览字节（供层② 上云）。长边压到 max_side 内，
    再按质量梯度（85→45）下探直到 ≤ max_bytes。这是唯一允许离开本地的图像产物。"""
    out = _resized(img.convert("RGB"), max_side)
    for quality in (85, 75, 65, 55, 45):
        buf = io.BytesIO()
        out.save(buf, format="JPEG", quality=quality, optimize=True)
        data = buf.getvalue()
        if len(data) <= max_bytes:
            return data
    return data  # 最低质量仍超限：返回它，尺寸约束优先于字节约束
