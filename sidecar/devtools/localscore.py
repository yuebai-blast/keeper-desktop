"""调试工具：对单张本地图片跑层① 评分并打印完整明细。

用法：
  mise run localscore -- /path/to/img.jpg
  mise run localscore -- /path/to/raw.cr2 --companion /path/to/raw.jpg

用于在真实照片上标定 keeper_engine/prescreen.py 顶部的阈值——光看总分不够，
要看分项怎么来的。首次会触发模型加载（之后同进程内很快）。

这是开发/标定脚本，不属于生产引擎包 keeper_engine，故放在 devtools/ 下。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 让脚本无论从哪运行都能 import keeper_engine（sidecar 根目录在 devtools/ 的上一级）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from keeper_engine import prescreen  # noqa: E402 —— 须在 sys.path 注入之后才能导入


def main() -> None:
    ap = argparse.ArgumentParser(description="层① 本地评分（单图，打印完整明细）")
    ap.add_argument("path", help="图片路径（jpg/png/heic/RAW）")
    ap.add_argument("--companion", action="append", default=[], help="RAW 的同名伴随图，可多次")
    args = ap.parse_args()

    ls = prescreen.assess_photo(args.path, tuple(args.companion))
    d = ls.detail

    print(f"\n  {ls.path}")
    print(f"  最终分: {ls.score}      头条理由: {ls.primary_reason or '（无明显问题）'}")
    if d is None:
        return
    print("  ── 明细 ──────────────────────────────")
    print(f"  基础分(扣分前): {d.base}")
    print(f"  技术质量[{d.tech_source}]: {d.tech_quality}    CLIP-IQA+(美学): {d.clipiqa}")
    print(f"  主体锐度: {d.sharpness}  →  归一 {d.sharpness_norm}")
    print(f"  曝光: 亮度均值 {d.brightness_mean} / 对比度 {d.contrast} / "
          f"欠曝比 {d.underexposed_ratio} / 过曝比 {d.overexposed_ratio}")
    print(f"  信息熵: {d.entropy}")
    f = d.face
    if f.count:
        print(f"  人脸: {f.count} 张   主脸→ 面积占比 {f.main_area_ratio} / 置信 {f.main_det_score} / "
              f"人脸区锐度 {f.main_sharpness} / 闭眼EAR {f.main_eye_ear}")
    else:
        print("  人脸: 未检到")
    if d.penalties:
        print("  扣分项（全部）:")
        for p in d.penalties:
            print(f"    -{p.points:<5} {p.reason}")
    else:
        print("  扣分项: 无")
    print()


if __name__ == "__main__":
    main()
