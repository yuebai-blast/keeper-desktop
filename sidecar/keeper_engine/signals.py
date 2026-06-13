"""纯 numpy/cv2 图像信号——无任何模型依赖，便于单测。

层① 的「技术质量」骨架：锐度、曝光、熵、显著/人脸区锐度、闭眼 EAR。
这些信号本身不下结论（不硬拒），只产出原始指标，由 prescreen 合成 0–100 分。
思路借鉴 ../pianke 的 quality.py / fast_quality.py，按 Keeper 需要重写。
"""

from __future__ import annotations

import cv2
import numpy as np


def center_crop(arr: np.ndarray, ratio: float) -> np.ndarray:
    """取中心 ratio 比例的子图（ratio ∈ (0,1]）。"""
    h, w = arr.shape[:2]
    ch = max(1, int(h * ratio))
    cw = max(1, int(w * ratio))
    y0 = (h - ch) // 2
    x0 = (w - cw) // 2
    return arr[y0:y0 + ch, x0:x0 + cw]


def laplacian_variance(gray: np.ndarray) -> float:
    """拉普拉斯方差——经典锐度指标，越大越锐。图过小返回 0。"""
    if gray.shape[0] < 3 or gray.shape[1] < 3:
        return 0.0
    center = gray[1:-1, 1:-1] * 4
    lap = center - gray[:-2, 1:-1] - gray[2:, 1:-1] - gray[1:-1, :-2] - gray[1:-1, 2:]
    return float(lap.var())


def tenengrad(gray: np.ndarray) -> float:
    """Sobel 梯度平方和。比拉普拉斯方差对噪点更鲁棒，作锐度的第二信号。"""
    if gray.shape[0] < 3 or gray.shape[1] < 3:
        return 0.0
    gx = gray[1:-1, 2:] - gray[1:-1, :-2]
    gy = gray[2:, 1:-1] - gray[:-2, 1:-1]
    return float((gx * gx + gy * gy).mean())


def entropy(gray: np.ndarray) -> float:
    """灰度直方图信息熵（bits，0–8）。越低越「信息贫乏」（纯色墙、严重欠曝等）。"""
    hist, _ = np.histogram(gray, bins=256, range=(0, 255), density=False)
    total = hist.sum()
    if total <= 0:
        return 0.0
    p = hist.astype(np.float64) / total
    p = p[p > 0]
    return float(-(p * np.log2(p)).sum())


def exposure_signals(gray: np.ndarray) -> dict:
    """曝光/对比度信号：均值亮度、对比度（标准差）、欠曝/过曝死区占比。"""
    return {
        "brightness_mean": float(gray.mean()),
        "contrast": float(gray.std()),
        "underexposed_ratio": float((gray <= 8).mean()),
        "overexposed_ratio": float((gray >= 247).mean()),
    }


def _saliency_map(gray: np.ndarray) -> np.ndarray | None:
    """用 cv2.saliency 的谱残差法算显著图（float32 0–1）。

    opencv-contrib 提供 StaticSaliencySpectralResidual（见 CLAUDE.md：刻意保住 contrib）。
    返回 None 表示算不出有效显著图（图过小 / 响应平坦），按数据不足处理、非降级。
    """
    if gray.shape[0] < 16 or gray.shape[1] < 16:
        return None
    try:
        sal = cv2.saliency.StaticSaliencySpectralResidual_create()
        ok, smap = sal.computeSaliency(gray.astype(np.uint8))
    except Exception:
        return None
    if not ok or smap is None:
        return None
    smap = smap.astype(np.float32)
    mn, mx = float(smap.min()), float(smap.max())
    if mx - mn < 1e-8 or smap.std() < 0.01:
        return None
    return (smap - mn) / (mx - mn)


def region_sharpness(gray: np.ndarray, bbox: tuple[int, int, int, int] | None = None) -> float | None:
    """衡量「该清晰的地方糊不糊」。

    - bbox 给定（人像选片：人脸框）：直接算该区域的拉普拉斯方差——最可靠。
    - bbox=None：回退用 cv2.saliency 取主体高响应区（前 20% 像素）算方差；
      显著图算不出再回退中心 60%。
    返回 None 表示数据不足（区域太小等），非降级。
    """
    if bbox is not None:
        x1, y1, x2, y2 = bbox
        h, w = gray.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        if x2 - x1 < 3 or y2 - y1 < 3:
            return None
        return laplacian_variance(gray[y1:y2, x1:x2])

    smap = _saliency_map(gray)
    if smap is None:
        return laplacian_variance(center_crop(gray, 0.6))
    thr = float(np.quantile(smap, 0.80))
    mask = smap >= thr
    if mask.sum() < 100 or gray.shape[0] < 3 or gray.shape[1] < 3:
        return laplacian_variance(center_crop(gray, 0.6))
    center = gray[1:-1, 1:-1] * 4
    lap = center - gray[:-2, 1:-1] - gray[2:, 1:-1] - gray[1:-1, :-2] - gray[1:-1, 2:]
    sel = lap[mask[1:-1, 1:-1]]
    if sel.size < 100:
        return laplacian_variance(center_crop(gray, 0.6))
    return float(sel.var())


def ear(eye_pts: np.ndarray) -> float:
    """单眼 Eye Aspect Ratio：(|p1-p5|+|p2-p4|) / (2|p0-p3|)。

    eye_pts 为 6 个 (x,y) 点。睁眼典型 0.25–0.35+，闭眼 < 0.2。横距为 0 时返回 0。
    """
    p = np.asarray(eye_pts, dtype=np.float32)
    vert1 = float(np.linalg.norm(p[1] - p[5]))
    vert2 = float(np.linalg.norm(p[2] - p[4]))
    horiz = float(np.linalg.norm(p[0] - p[3]))
    if horiz < 1e-6:
        return 0.0
    return (vert1 + vert2) / (2.0 * horiz)
