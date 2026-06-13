"""层①（本地模型漏斗）：对组内每张照片打 0–100 分（技术质量为主）。

合成思路（不做硬拒，硬阈值交给 funnel）：
  base = 0.45·TOPIQ + 0.20·CLIP-IQA+ + 0.35·主体锐度(归一)   → 0–100
  再对「闭眼 / 人脸脱焦 / 欠过曝 / 画面单调」等问题扣分。
其中主体锐度优先用「人脸框」内的拉普拉斯方差（人像选片更准），无脸时回退显著区。
扣分项里优先级最高的那个翻成中文短 reason，作为可解释去留理由。

阈值都是可调旋钮（在真实照片上标定），集中在下方常量。详见 docs/product-flow.md。
"""

from __future__ import annotations

import math

from . import imaging, signals, vision
from .models import FaceDetail, Group, LocalScore, Penalty, ScoreDetail

# ── 可调阈值（锐度类指标在 768 长边灰度上计算）──────────────────────────────
SHARP_LOG_REF = math.log1p(400.0)  # 主体锐度归一参考：log1p(var)/此值 → ~[0,1]
IMG_VERY_BLUR = 30.0               # 无脸时整图主体锐度低于此 → 脱焦
FACE_VERY_BLUR = 60.0              # 主脸锐度低于此 → 人脸脱焦
FACE_BLUR = 150.0                  # 主脸锐度低于此 → 人脸偏糊
EYES_CLOSED_EAR = 0.18            # 主脸 EAR 低于此 → 闭眼
DET_MIN = 0.5                      # 人脸最低置信度（低于此当背景误检）
FACE_MIN_AREA = 0.005             # 人脸面积占比下限（闭眼/糊脸规则才适用）
DARK_MEAN = 45.0                   # 均值亮度低于此 → 欠曝
BRIGHT_MEAN = 210.0                # 均值亮度高于此 → 过曝
CLIP_DARK_RATIO = 0.45            # 死黑像素占比高于此 → 欠曝
CLIP_BRIGHT_RATIO = 0.40          # 死白像素占比高于此 → 过曝
LOW_ENTROPY = 3.0                  # 信息熵低于此 → 画面单调
LOW_IQA = 0.40                     # TOPIQ 与 CLIP-IQA 同时低于此 → 观感平庸


def assess_group(group: Group) -> list[LocalScore]:
    """对一个组内每张图打 0–100 本地技术质量分（无 companion 信息）。

    任一张失败即抛出——供测试与「干净输入」的内部调用；/assess 端点逐张容错另算。
    """
    return [assess_photo(p) for p in group.photos]


def assess_photo(path: str, companions: tuple[str, ...] | list[str] = ()) -> LocalScore:
    """对单张照片打 0–100 本地分 + 中文 reason + 完整明细。读图/推理失败抛异常。"""
    img = imaging.load_for_analysis(path, companions)
    gray = imaging.to_gray_array(img, max_side=768)

    faces = vision.extract_faces(img)
    main, main_sharp = _main_face_sharpness(faces, img, gray)

    exposure = signals.exposure_signals(gray)
    ent = signals.entropy(gray)

    # 技术质量：有脸用 TOPIQ-nr-face 评人脸裁剪（人像更贴合），无脸用通用 TOPIQ-nr 评整图。
    # topiq_nr-face 内部自带人脸检测，检不到会 AssertionError——此时回退通用 topiq_nr（不视为失败）。
    # 注意：只接 AssertionError；模型加载失败抛的 VisionUnavailable 仍照常上抛，不静默降级。
    tech, tech_source = None, "topiq_nr"
    if main is not None:
        try:
            tech = _clamp01(vision.topiq_face_score(_crop_face(img, main["bbox"])))
            tech_source = "topiq_nr-face"
        except AssertionError:
            tech = None
    if tech is None:
        tech = _clamp01(vision.topiq_score(img))
        tech_source = "topiq_nr"
    clipiqa = _clamp01(vision.clipiqa_plus_score(img))

    effective_sharp = main_sharp if main_sharp is not None else signals.region_sharpness(gray)
    sharp_norm = _clamp01(math.log1p(max(0.0, effective_sharp or 0.0)) / SHARP_LOG_REF)
    base = (0.45 * tech + 0.20 * clipiqa + 0.35 * sharp_norm) * 100.0

    # 人脸眼睛信号（main 算一次；全员闭眼需逐张高置信脸的 EAR）
    main_eye = vision.eye_open_score(main) if main is not None else None
    main_big = main is not None and main.get("_area_ratio", 0) >= FACE_MIN_AREA
    high_conf = [f for f in faces if f["det_score"] >= DET_MIN and f.get("_area_ratio", 0) >= FACE_MIN_AREA]
    all_closed = len(high_conf) >= 2 and all(
        (e := vision.eye_open_score(f)) is not None and e < EYES_CLOSED_EAR for f in high_conf
    )

    hits = _evaluate_penalties(
        main_present=main is not None, main_big=main_big, main_eye=main_eye, all_closed=all_closed,
        main_sharp=main_sharp, effective_sharp=effective_sharp, exposure=exposure,
        entropy=ent, tech=tech, clipiqa=clipiqa,
    )
    reason = hits[0][0] if hits else ""
    score = float(max(0.0, min(100.0, base - sum(p for _, p in hits))))

    detail = ScoreDetail(
        base=round(base, 2),
        tech_quality=round(tech, 4), tech_source=tech_source, clipiqa=round(clipiqa, 4),
        sharpness=round(effective_sharp, 2) if effective_sharp is not None else None,
        sharpness_norm=round(sharp_norm, 4), entropy=round(ent, 3),
        brightness_mean=round(exposure["brightness_mean"], 2),
        contrast=round(exposure["contrast"], 2),
        underexposed_ratio=round(exposure["underexposed_ratio"], 4),
        overexposed_ratio=round(exposure["overexposed_ratio"], 4),
        face=FaceDetail(
            count=len(high_conf),
            main_area_ratio=round(main["_area_ratio"], 4) if main is not None else None,
            main_det_score=round(main["det_score"], 4) if main is not None else None,
            main_sharpness=round(main_sharp, 2) if main_sharp is not None else None,
            main_eye_ear=main_eye,
        ),
        penalties=[Penalty(reason=r, points=p) for r, p in hits],
    )
    return LocalScore(path=path, score=round(score, 2), primary_reason=reason, detail=detail)


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def _crop_face(img, bbox, margin: float = 0.3):
    """从原图裁出主脸区（带 margin 余量）供人脸 IQA 用。区域退化时退回整图。"""
    w, h = img.size
    x1, y1, x2, y2 = bbox
    mx, my = int((x2 - x1) * margin), int((y2 - y1) * margin)
    x1, y1 = max(0, x1 - mx), max(0, y1 - my)
    x2, y2 = min(w, x2 + mx), min(h, y2 + my)
    rgb = img.convert("RGB")
    if x2 - x1 < 2 or y2 - y1 < 2:
        return rgb
    return rgb.crop((x1, y1, x2, y2))


def _main_face_sharpness(faces, img, gray):
    """挑「主脸」（置信度够、面积最大），返回 (main_face_or_None, 主脸锐度_or_None)。"""
    w, h = img.size
    area = float(w * h) or 1.0
    candidates = []
    for f in faces:
        if f["det_score"] < DET_MIN:
            continue
        x1, y1, x2, y2 = f["bbox"]
        f["_area_ratio"] = max(0.0, (x2 - x1)) * max(0.0, (y2 - y1)) / area
        candidates.append(f)
    if not candidates:
        return None, None
    main = max(candidates, key=lambda f: f["_area_ratio"])

    # 把原图坐标的人脸框缩放到 768 灰度坐标
    gh, gw = gray.shape[:2]
    sx, sy = gw / float(w), gh / float(h)
    x1, y1, x2, y2 = main["bbox"]
    bbox = (int(x1 * sx), int(y1 * sy), int(x2 * sx), int(y2 * sy))
    return main, signals.region_sharpness(gray, bbox)


def _evaluate_penalties(*, main_present, main_big, main_eye, all_closed, main_sharp,
                        effective_sharp, exposure, entropy, tech, clipiqa):
    """纯函数：按规则返回所有触发的扣分项 [(中文原因, 扣分)]，按优先级排序（首项即 reason）。

    优先级思路：闭眼/人脸最敏感且最确信；曝光是确信信号，排在「无脸整图脱焦」这个较弱
    启发式之前（纯黑/纯白图本就无细节，应报欠/过曝而非误判脱焦）。
    """
    under = exposure["brightness_mean"] < DARK_MEAN or exposure["underexposed_ratio"] >= CLIP_DARK_RATIO
    over = exposure["brightness_mean"] > BRIGHT_MEAN or exposure["overexposed_ratio"] >= CLIP_BRIGHT_RATIO

    rules = [
        (all_closed, 35.0, "全员闭眼"),
        (main_big and main_eye is not None and main_eye < EYES_CLOSED_EAR, 28.0, "闭眼"),
        (main_sharp is not None and main_sharp < FACE_VERY_BLUR, 25.0, "人脸脱焦"),
        (main_sharp is not None and FACE_VERY_BLUR <= main_sharp < FACE_BLUR, 12.0, "人脸偏糊"),
        (under, 15.0, "欠曝"),
        (over, 15.0, "过曝"),
        (not main_present and (effective_sharp or 0.0) < IMG_VERY_BLUR, 18.0, "脱焦"),
        (entropy < LOW_ENTROPY, 8.0, "画面单调"),
        (tech < LOW_IQA and clipiqa < LOW_IQA, 8.0, "观感平庸"),
    ]
    return [(reason, points) for hit, points, reason in rules if hit]
