"""分组（漏斗前的第 0 步）：把相似连拍聚成「瞬间组」。

  - 语义特征：DINOv2
  - 聚类：基于特征相似度 + 拍摄时间 + 人脸
"""

from __future__ import annotations

from .models import Group


def group_photos(photo_paths: list[str]) -> list[Group]:
    """对一批照片分组，返回若干「瞬间组」。"""
    raise NotImplementedError("待实现分组")
