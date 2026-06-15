"""影像IO地基：读图、转分析数组、生成低清预览。

分组、层①、层② 都依赖它。两条产品原则在这里落地：
  - 读 RAW 只取内嵌 JPEG 预览（毫秒级、不做 demosaic），原图不改不传。
  - `make_preview` 生成的低清预览是「唯一允许上云」的产物（供层② 用，用完即焚）。
失败一律抛异常——不静默降级（CLAUDE.md）。
"""

from __future__ import annotations

import io
import os
from datetime import datetime
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


def make_thumbnail(img: Image.Image, max_side: int = 256, quality: int = 80) -> bytes:
    """生成小缩略图 JPEG 字节，供桌面端画廊显示。

    走 sidecar 而非 webview 直读，是因为它能解 RAW/HEIC 并统一缩放——浏览器做不到。
    """
    out = _resized(img.convert("RGB"), max_side)
    buf = io.BytesIO()
    out.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def cached_thumbnail(path: str, max_side: int = 256, quality: int = 80) -> bytes:
    """带磁盘缓存的缩略图。命中缓存直接读盘，否则生成并落盘。

    缓存就近落在原图同目录的 `.thumbnails/` 子目录，文件名 `{stem}@{size}.jpg`。
    workspace 副本是只读不变的——所以缓存键只需 stem+尺寸，无需哈希/mtime 失效判断；
    缓存随项目 workspace 一起被 rmtree 清理，不留全局孤儿。
    文件不存在则 os.stat 抛 FileNotFoundError（由端点转 404）。
    """
    src = Path(path)
    os.stat(src)  # 不存在 → FileNotFoundError
    thumbs_dir = src.parent / ".thumbnails"
    thumbs_dir.mkdir(parents=True, exist_ok=True)
    cache_file = thumbs_dir / f"{src.stem}@{max_side}.jpg"
    if cache_file.exists():
        return cache_file.read_bytes()

    jpeg = make_thumbnail(load_for_analysis(path), max_side=max_side, quality=quality)
    tmp = cache_file.with_name(cache_file.name + ".tmp")  # 原子写：临时文件 + rename
    tmp.write_bytes(jpeg)
    tmp.replace(cache_file)
    return jpeg


def read_capture_time(img: Image.Image) -> datetime | None:
    """从 EXIF 读拍摄时间（DateTimeOriginal + 亚秒）。读不到返回 None（按未知处理）。

    分组用它做「时间邻近」信号：同一串连拍时间挨得很近。RAW 走内嵌预览/companion 时
    通常仍带 EXIF；实在没有就退化为只靠语义相似度。
    """
    try:
        exif = img.getexif()
        ifd = exif.get_ifd(0x8769)  # Exif 子 IFD
        dt_str = ifd.get(36867) or exif.get(306)  # DateTimeOriginal / DateTime
        if not dt_str:
            return None
        dt = datetime.strptime(str(dt_str).strip(), "%Y:%m:%d %H:%M:%S")
        subsec = str(ifd.get(37521, "")).strip()  # SubSecTimeOriginal
        if subsec.isdigit():
            dt = dt.replace(microsecond=int(subsec.ljust(6, "0")[:6]))
        return dt
    except Exception:
        return None


def read_gps(img: Image.Image) -> tuple[float, float] | None:
    """从 EXIF 读拍摄地经纬度（十进制度，WGS-84）。读不到/无 GPS 返回 None。

    用于「拍摄地」展示（坐标再交由在线地理编码反查地名）。度分秒按 ref（N/S/E/W）定正负。
    照片本身永不出本地，只有反查时把坐标发给地理编码服务（见 client.geocode_client）。
    """
    try:
        gps = img.getexif().get_ifd(0x8825)  # GPS IFD
        if not gps:
            return None
        lat = _dms_to_deg(gps.get(2), gps.get(1))   # GPSLatitude / GPSLatitudeRef
        lon = _dms_to_deg(gps.get(4), gps.get(3))   # GPSLongitude / GPSLongitudeRef
        if lat is None or lon is None:
            return None
        return lat, lon
    except Exception:
        return None


def _dms_to_deg(dms, ref) -> float | None:
    """(度,分,秒) + 参考方向 → 带符号十进制度。任一缺失返回 None。"""
    if not dms or ref is None:
        return None
    try:
        d, m, s = (float(x) for x in dms)
    except (TypeError, ValueError):
        return None
    deg = d + m / 60.0 + s / 3600.0
    if str(ref).strip().upper() in ("S", "W"):
        deg = -deg
    return deg
