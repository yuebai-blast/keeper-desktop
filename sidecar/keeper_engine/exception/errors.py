"""领域异常集中定义。

不静默降级（CLAUDE.md）：本地模型依赖缺失/加载失败、层② 打分不可用，一律抛出对应异常，
绝不悄悄退化。各 client/service 抛这里的异常，controller 翻译成 HTTP 状态码。
"""

from __future__ import annotations


class VisionUnavailable(RuntimeError):
    """本地模型不可用（权重下载/加载失败）。通常可重试（网络等）。绝不静默降级，一律抛出。"""


class DependencyMissing(VisionUnavailable):
    """运行依赖缺失（Python 包未安装）——属于「不允许运行」，重试也无用，不可恢复。"""


class ScorerError(RuntimeError):
    """层② 打分不可用（缺 key / 网络 / 接口或解析错误）。不静默降级，一律抛出。"""
