"""层① / 分组模型的就绪态 + 启动期预热。

后台预热线程一次性下载+载入全部本地模型，期间 /health 报 loading，就绪转 ready、失败转 error。
这样模型在第一个请求之前就备好，且加载失败能在启动期经 /health 暴露——
既不让首个请求卡几分钟，又不「假装健康」（不静默降级）。
"""

from __future__ import annotations

import logging
import threading

from ..client.vision_client import VisionClient

logger = logging.getLogger("keeper_engine.service.readiness")


class ReadinessService:
    """模型就绪状态（loading/ready/error）+ 后台预热。DI 单例，全局共享。"""

    def __init__(self, vision: VisionClient) -> None:
        self._vision = vision
        self.status = "loading"  # loading（预热中）| ready（可服务）| error（加载失败，detail 含原因）
        self.detail = ""

    def start_warmup(self) -> None:
        """启动后台预热线程，不阻塞调用方（在 app lifespan 里调用）。"""
        threading.Thread(target=self._warmup, name="keeper-warmup", daemon=True).start()

    def _warmup(self) -> None:
        """一次性预热分组 + 层① 全部模型；失败不崩进程，记入就绪状态经 /health 上报。"""
        try:
            self._vision.require_grouping_capabilities()
            self._vision.require_layer1_capabilities()
            self.status = "ready"
            logger.info("readiness: 分组 + 层① 模型预热完成，服务就绪")
        except Exception as e:  # noqa: BLE001 —— 捕获以经 /health 上报，而非让线程静默死掉
            self.status = "error"
            self.detail = f"{type(e).__name__}: {e}"
            logger.error("readiness: 层① 模型预热失败：%s", self.detail)
