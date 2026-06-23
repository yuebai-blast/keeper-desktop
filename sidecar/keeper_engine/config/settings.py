"""集中配置类——启动初始化一次，由 DI 以单例注入。

可配置项从「配置文件 {home}/config.toml」与「环境变量（KEEPER_ 前缀）」加载，优先级：
构造参数 > 环境变量 > 配置文件 > 字段默认值。派生路径与固定常量写死在类里，不对外暴露为配置。

所有本地资源统一放在数据根 home（dev 默认 ~/.keeper；prod 由 Tauri 注入 app_data_dir）下：
config.toml 配置、models/ 模型、workspace/ 项目副本、keeper.db 状态库、ark_key 大模型 key（0600）。
config.toml 的读取位置必须与写入端（settings_service）一致地跟随 home，否则 prod 写进
app_data_dir 的配置会从 ~/.keeper 读不回来。缩略图就近缓存在各 workspace 项目的 .thumbnails/
（随项目清理，不占全局目录）。子路径均由 home 派生（computed）。算法标定阈值随各自模块就近保留，不在此。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import ClassVar

from pydantic import computed_field, field_validator, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

# home 默认数据根（dev）；prod 经环境变量 KEEPER_HOME 覆盖（与 home 字段默认一致）。
_DEFAULT_HOME = Path.home() / ".keeper"


class Settings(BaseSettings):
    """运行期配置。改 {home}/config.toml 或设 KEEPER_* 环境变量即可覆盖。"""

    model_config = SettingsConfigDict(env_prefix="KEEPER_", extra="ignore")

    # ── 固定常量（代码逻辑固定，不可配）──
    # 桌面端 Tauri webview 跨源调用本服务，放行本地来源（服务只绑 127.0.0.1，安全）
    cors_origin_regex: ClassVar[str] = r"^(https?://(localhost|127\.0\.0\.1)(:\d+)?|tauri://localhost)$"

    # ── 可配置项 ──
    home: Path = _DEFAULT_HOME  # 统一数据根（env KEEPER_HOME 覆盖）
    host: str = "127.0.0.1"               # 仅本机；main.py 的 --host/--port 可再覆盖
    port: int = 8761
    device: str = ""                      # ""=自动（CPU，有 CUDA 用 CUDA）/ "cuda" / "cpu"
    dino_model: str = "facebook/dinov2-small"
    face_pack: str = "buffalo_l"
    # sidecar HTTP 鉴权 token：prod 由 Tauri 壳启动时生成并经 env 注入；dev/独立运行留空=不鉴权。
    auth_token: str = ""
    # 层② 大模型（火山 Ark，OpenAI 兼容）；模型 id 必须由配置/环境提供，默认空作兜底占位
    ark_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    ark_model: str = ""
    ark_concurrency: int = 4
    # 层① 本地评分组内并发度（逐张并行）。默认 1=串行：CPU/MPS 上 torch/onnxruntime 已用
    # intra-op 多线程吃满核，再在上层并发多张图无真实收益，只增峰值内存与抖动（参考 pianke
    # 经验：MPS/CPU 固定单线程最稳）。仅 CUDA 等场景才值得经 KEEPER_LOCAL_CONCURRENCY 调大；
    # 并发开启时 pyiqa 推理的线程安全已由 VisionClient 的 per-model 锁兜底。
    local_concurrency: int = 1
    # 火山「管理面 OpenAPI」地域：仅用于 AK/SK 调 ListFoundationModels 拉取可选模型列表（自用版便利功能）；
    # 与推理用的 ARK_API_KEY 是两套鉴权。当前火山方舟管理面仅 cn-beijing。
    volc_region: str = "cn-beijing"

    # 模型缓存目录：prod 由 Tauri 壳指向 app_cache_dir（大缓存不进备份），dev 默认在 home 下。
    # None=未显式配置→构造后派生为 home/models（保持与历史一致）。
    models_dir: Path | None = None  # env KEEPER_MODELS_DIR

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

    @model_validator(mode="after")
    def _derive_models_dir(self) -> "Settings":
        # 未显式提供 models_dir（env/配置/构造参数都没给）时，派生为 home/models。
        if self.models_dir is None:
            self.models_dir = self.home / "models"
        return self

    # ── 派生路径（由 home 计算，不单独配置）──
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

    # 火山管理面 AK/SK：与 ark_key 同款——各一个文件、0600、绝不入库（机密隔离爆炸半径，见设计讨论）。
    @computed_field
    @property
    def volc_ak_file(self) -> Path:
        return self.home / "volc_ak"

    @computed_field
    @property
    def volc_sk_file(self) -> Path:
        return self.home / "volc_sk"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # config.toml 必须跟数据根 home 走（与写入端 settings_service 一致），否则 prod 写到
        # app_data_dir 的配置会从默认 ~/.keeper 读不回来。home 不能由 config.toml 自身决定
        # （那样循环），故在此按「构造参数 > 环境变量 KEEPER_HOME > 默认」解析其位置——与 home 字段同序。
        home = init_settings.init_kwargs.get("home") or os.environ.get("KEEPER_HOME") or _DEFAULT_HOME
        toml_source = TomlConfigSettingsSource(settings_cls, toml_file=Path(home) / "config.toml")
        # 优先级：构造参数 > 环境变量 > 配置文件（toml）
        return init_settings, env_settings, toml_source
