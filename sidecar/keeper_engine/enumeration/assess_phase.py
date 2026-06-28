"""评测进度阶段——驱动前端实时进度条的文案与展示。"""

from __future__ import annotations

from enum import Enum


class AssessPhase(str, Enum):
    """评测进度阶段。前端镜像同名常量，改任一端两端同步。"""

    IDLE = "IDLE"        # 空闲：当前项目没有正在跑的评测
    LAYER1 = "LAYER1"    # 层①本地评分中（逐张串行最慢，最该看进度）
    LAYER2 = "LAYER2"    # 层②大模型打分中（并发，按完成数推进）
    EMBED = "EMBED"      # 分组：逐张取特征（DINOv2+人脸），最慢，报精确 done/total
    CLUSTER = "CLUSTER"  # 分组：聚类中（O(n²) 人脸矩阵），不确定态，不报具体计数
    DONE = "DONE"        # 本轮评测/分组已结束
