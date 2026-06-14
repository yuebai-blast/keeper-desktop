"""分组 / 层① 模型的就绪态 + 启动期预热（逐模型报进度）。

启动即一次性加载全部模型（不静默降级）：
  - 依赖缺失（DependencyMissing，Python 包未装）→ 致命、**不可重试**：属于「不允许运行」。
  - 权重下载/加载失败（VisionUnavailable 等，多为网络）→ **可重试**：前端给重试按钮。
预热期间 /health 报 loading + 进度（current/total/step），就绪转 ready、失败转 error。
first_run（预热前模型缓存是否为空）供前端区分「首次下载」与「常规加载」两种进入方式。
"""

from __future__ import annotations

import logging
import threading

from ..client.vision_client import VisionClient
from ..config.settings import Settings
from ..exception.errors import DependencyMissing

logger = logging.getLogger("keeper_engine.service.readiness")

# 视为「模型已下载过」的权重文件后缀（任一存在即非首次）
_WEIGHT_SUFFIXES = (".onnx", ".safetensors", ".bin", ".pth", ".pt")


class ReadinessService:
    """模型就绪状态机：loading / ready / error，带进度、可重试标记与首次下载标记。DI 单例。"""

    def __init__(self, vision: VisionClient, settings: Settings) -> None:
        self._vision = vision
        self._settings = settings
        self._lock = threading.Lock()
        self.status = "loading"      # loading（预热中）| ready（可服务）| error（失败）
        self.detail = ""
        self.retryable = False       # error 时是否可重试（依赖缺失=False）
        self.first_run = self._detect_first_run()  # 预热前探测：模型缓存是否为空（需下载）
        self.current = 0             # 已完成的步骤数
        self.total = 0               # 总步骤数
        self.step = ""               # 当前正在加载的步骤名

    def _detect_first_run(self) -> bool:
        """模型缓存目录里没有任何权重文件 → 视为首次（需联网下载）。"""
        root = self._settings.models_dir
        if not root.exists():
            return True
        return not any(any(root.rglob(f"*{suffix}")) for suffix in _WEIGHT_SUFFIXES)

    def snapshot(self) -> dict:
        """对外（/health）暴露的就绪态快照。"""
        return {
            "status": self.status,
            "detail": self.detail,
            "retryable": self.retryable,
            "first_run": self.first_run,
            "progress": {"current": self.current, "total": self.total, "step": self.step},
        }

    def start_warmup(self) -> None:
        """启动后台预热线程，不阻塞调用方（在 app lifespan 里调用）。"""
        threading.Thread(target=self._warmup, name="keeper-warmup", daemon=True).start()

    def _warmup(self) -> None:
        """逐个加载全部模型并更新进度；失败按「是否依赖缺失」区分可否重试，记入就绪态。"""
        steps = self._vision.warmup_steps()
        self.total = len(steps)
        for i, (label, load) in enumerate(steps):
            self.step = label
            self.current = i
            try:
                load()
            except DependencyMissing as e:
                self.status, self.retryable = "error", False
                self.detail = f"运行依赖缺失，无法启动：{e}"
                logger.error("readiness: 依赖缺失，拒绝运行：%s", e)
                return
            except Exception as e:  # noqa: BLE001 —— 下载/加载失败可重试，经 /health 上报
                self.status, self.retryable = "error", True
                self.detail = f"{type(e).__name__}: {e}"
                logger.error("readiness: 模型加载失败（可重试）：%s", self.detail)
                return
            self.current = i + 1
        self.step = ""
        self.status = "ready"
        logger.info("readiness: 全部模型就绪（%d 项）", self.total)

    def retry(self) -> bool:
        """重新预热——仅在「可重试的 error」时生效；返回是否已触发。"""
        with self._lock:
            if self.status != "error" or not self.retryable:
                return False
            self.status, self.detail, self.current, self.step = "loading", "", 0, ""
            self.start_warmup()
            return True
