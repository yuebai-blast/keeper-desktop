"""项目生命周期状态——驱动前端页面流转与恢复。"""

from __future__ import annotations

from enum import Enum


class ProjectStatus(str, Enum):
    """项目状态机：建项目并复制副本 → 分组 → 用户选择 → 完成。"""

    GROUPING = "GROUPING"      # 已建项目+复制副本，待/正在分组
    SELECTING = "SELECTING"    # 已分组，用户在分组列表中选择
    COMPLETED = "COMPLETED"    # 已归档到目标文件夹、清理 workspace
