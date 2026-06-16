"""设置页端点（自用版）：读/写大模型配置（key / 模型 id / 基址）。

只接线（解析请求 → 调 service → 返回）。**仅自用版注册**——商业版构建移除本 controller，
key 由云端中转持有，不下发客户端（见 .todolist.md 版本区分方案）。
"""

from __future__ import annotations

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from ..container import Container
from ..request.settings_request import UpdateSettingsRequest
from ..response.envelope import EnvelopeRoute
from ..response.settings_response import SettingsView
from ..service.settings_service import SettingsService

router = APIRouter(route_class=EnvelopeRoute)


@router.get("/settings", response_model=SettingsView)
@inject
def get_settings(
    svc: SettingsService = Depends(Provide[Container.settings_service]),
) -> SettingsView:
    """当前大模型配置（不含 key 明文，只报告 ark_key_set）。"""
    return svc.get()


@router.post("/settings", response_model=SettingsView)
@inject
def update_settings(
    req: UpdateSettingsRequest,
    svc: SettingsService = Depends(Provide[Container.settings_service]),
) -> SettingsView:
    """更新大模型配置（部分更新）。key 写入 0600 文件，model/base_url 落 config.toml 并即时生效。"""
    return svc.update(req)
