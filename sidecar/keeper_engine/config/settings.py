"""集中配置类——启动初始化一次，由 DI 以单例注入。

可配置项从「配置文件 ~/.keeper/config.toml」与「环境变量（KEEPER_ 前缀）」加载，优先级：
构造参数 > 环境变量 > 配置文件 > 字段默认值。派生路径与固定常量写死在类里，不对外暴露为配置。

所有本地资源统一放在数据根 home（默认 ~/.keeper）下：models/ 模型、workspace/ 项目副本、
keeper.db 状态库、ark_key 大模型 key（0600）。缩略图就近缓存在各 workspace 项目的 .thumbnails/
（随项目清理，不占全局目录）。子路径均由 home 派生（computed）。
算法标定阈值随各自模块就近保留，不在此。
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from pydantic import computed_field, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

_CONFIG_FILE = Path.home() / ".keeper" / "config.toml"


class Settings(BaseSettings):
    """运行期配置。改 ~/.keeper/config.toml 或设 KEEPER_* 环境变量即可覆盖。"""

    model_config = SettingsConfigDict(env_prefix="KEEPER_", toml_file=_CONFIG_FILE, extra="ignore")

    # ── 固定常量（代码逻辑固定，不可配）──
    # 桌面端 Tauri webview 跨源调用本服务，放行本地来源（服务只绑 127.0.0.1，安全）
    cors_origin_regex: ClassVar[str] = r"^(https?://(localhost|127\.0\.0\.1)(:\d+)?|tauri://localhost)$"

    # ── 可配置项 ──
    home: Path = Path.home() / ".keeper"  # 统一数据根
    host: str = "127.0.0.1"               # 仅本机；main.py 的 --host/--port 可再覆盖
    port: int = 8761
    device: str = ""                      # ""=自动（CPU，有 CUDA 用 CUDA）/ "cuda" / "cpu"
    dino_model: str = "facebook/dinov2-small"
    face_pack: str = "buffalo_l"
    # 层② 大模型（火山 Ark，OpenAI 兼容）；模型 id 必须由配置/环境提供，默认空作兜底占位
    ark_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    ark_model: str = ""
    ark_concurrency: int = 4

    # 选片项目最终输出根目录（固定前缀，输出到 {output_root}/{项目名}）；不在 home 下，单独可配
    output_root: Path = Path.home() / "Pictures" / "Keeper"

    # 拍摄地在线反查地名（只发坐标、不发照片）；默认 OpenStreetMap Nominatim（无 key、WGS-84）
    geocode_enabled: bool = True
    geocode_url: str = "https://nominatim.openstreetmap.org/reverse"
    geocode_user_agent: str = "Keeper/0.1 (https://github.com/yuebai-blast)"
    geocode_lang: str = "zh-CN"

    @field_validator("device")
    @classmethod
    def _normalize_device(cls, v: str) -> str:
        return v.lower()

    # ── 派生路径（由 home 计算，不单独配置）──
    @computed_field
    @property
    def models_dir(self) -> Path:
        return self.home / "models"

    @computed_field
    @property
    def workspace_dir(self) -> Path:
        return self.home / "workspace"

    @computed_field
    @property
    def db_path(self) -> Path:
        return self.home / "keeper.db"

    @computed_field
    @property
    def ark_key_file(self) -> Path:
        return self.home / "ark_key"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # 优先级：构造参数 > 环境变量 > 配置文件（toml）
        return (init_settings, env_settings, TomlConfigSettingsSource(settings_cls))
