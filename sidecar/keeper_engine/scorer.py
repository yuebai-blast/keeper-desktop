"""层②（在线 LLM 漏斗）：大模型对候选打 0–100 分。

Scorer 抽象是全系统唯一会演化（本地直调 → 云端中转）的环节：
  - LocalDirectScorer（本版）：sidecar 直连大模型 API（火山 Ark，OpenAI 兼容协议）。
  - CloudRelayScorer（未来商业版）：改调自建云端中转层（鉴权 + 计量计费 + 加价）。
业务流程只依赖 Scorer 协议，商业化时新增实现 + 切配置即可，编排逻辑零改动。

注意：只上传低清预览，不传原图；推理完即焚。
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .models import Score


class Scorer(Protocol):
    """给一组候选预览打 0–100 分。"""

    def score(self, preview_paths: list[str]) -> list[Score]:
        ...


class LocalDirectScorer:
    """本版实现：sidecar 直连大模型 API。

    API key 本地管理：~/.config/keeper/（0600 权限），可由 UI 录入或环境变量注入，绝不入库。
    """

    CONFIG_KEY_FILE = Path.home() / ".config" / "keeper" / "ark_key"

    def __init__(self, model: str, api_key: str | None = None) -> None:
        self.model = model
        self.api_key = api_key  # None 时从 CONFIG_KEY_FILE / 环境变量解析

    def score(self, preview_paths: list[str]) -> list[Score]:
        """对每张低清预览调大模型打分。

        TODO: 实现调用与解析；prompt 输出 0–100 分 + 中文短理由。
        """
        raise NotImplementedError("待实现：直连大模型打分")
