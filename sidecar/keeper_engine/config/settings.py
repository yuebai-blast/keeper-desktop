"""集中的部署/运行配置——收口原先散落在各模块的环境变量读取。

这里只放「部署/运行配置」（服务地址、外部 API、设备、缓存目录等），由 DI 容器以单例注入
给各 client/service。算法**标定阈值**（grouping/prescreen/funnel 顶部的可调旋钮）属于算法参数，
不在这里，随各自模块就近保留。

无参构造即从环境变量取默认值（dependency-injector 的 Singleton(Settings) 会这样实例化）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _default_models_dir() -> Path:
    return Path(os.environ.get("KEEPER_MODELS_DIR", str(Path.home() / ".cache" / "keeper" / "models")))


@dataclass
class Settings:
    """运行期配置；字段默认值从环境变量读取，便于本地/打包环境覆盖。"""

    # ── 服务监听（仅本机；main.py 的 --host/--port 可再覆盖）──
    host: str = field(default_factory=lambda: os.environ.get("KEEPER_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(os.environ.get("KEEPER_PORT", "8761")))
    # 桌面端 Tauri webview 跨源调用本服务，放行本地来源（服务只绑 127.0.0.1，安全）
    cors_origin_regex: str = r"^(https?://(localhost|127\.0\.0\.1)(:\d+)?|tauri://localhost)$"

    # ── 本地模型（VisionClient）──
    device: str = field(default_factory=lambda: os.environ.get("KEEPER_DEVICE", "").lower())
    models_dir: Path = field(default_factory=_default_models_dir)
    dino_model: str = field(default_factory=lambda: os.environ.get("KEEPER_DINO_MODEL", "facebook/dinov2-small"))
    face_pack: str = field(default_factory=lambda: os.environ.get("KEEPER_FACE_PACK", "buffalo_l"))

    # ── 层② 大模型（火山 Ark，OpenAI 兼容；LocalDirectScorer）──
    ark_base_url: str = field(
        default_factory=lambda: os.environ.get("KEEPER_ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    )
    # 模型 id 必须由调用方/环境提供（不同账号开通的模型不同），这里只是兜底占位
    ark_model: str = field(default_factory=lambda: os.environ.get("KEEPER_ARK_MODEL", ""))
    ark_concurrency: int = field(default_factory=lambda: int(os.environ.get("KEEPER_ARK_CONCURRENCY", "4")))
    # API key 本地管理：env ARK_API_KEY 或此文件（0600），绝不入库（CLAUDE.md）
    ark_key_file: Path = field(default_factory=lambda: Path.home() / ".config" / "keeper" / "ark_key")
