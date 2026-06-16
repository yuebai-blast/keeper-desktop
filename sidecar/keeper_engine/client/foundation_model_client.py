"""火山「管理面 OpenAPI」客户端：拉取支持「图片内容理解」的基础模型列表（自用版便利功能）。

仅用于设置页「拉取视觉模型」下拉辅助，帮用户挑一个能看图打分的 model id——**不参与打分链路**。
打分仍只用 ARK_API_KEY（推理面）；这里用的是 AK/SK（管理面），两套鉴权互不相干。

实现说明：ListFoundationModels 在 SDK 5.0.34 的 ARKApi 里未封成类型化方法，故用 volcenginesdkcore
的通用调用器 UniversalApi 按 Action 名直发（AK/SK 签名由 SDK 处理）。按 TaskTypes=VisualQuestionAnswering
（图片内容理解）精准筛选——这正是层②「看图打分」所需的能力。
"""

from __future__ import annotations

import volcenginesdkcore

from ..config.settings import Settings
from ..vo.vision_model import VisionModel

# 管理面接口固定参数
_SERVICE = "ark"
_VERSION = "2024-01-01"
_ACTION = "ListFoundationModels"
# TaskTypes 取值「图片内容理解」= 我们层②看图打分所需能力（见火山 ListFoundationModels 文档）
_TASK_VQA = "VisualQuestionAnswering"


class FoundationModelClient:
    """调火山管理面 ListFoundationModels 拉取视觉模型。AK/SK 由调用方传入（不在本类持有）。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def list_vision_models(self, ak: str, sk: str) -> list[VisionModel]:
        """返回支持「图片内容理解」的基础模型列表。网络/鉴权/接口错误一律上抛，由 service 翻成业务码。"""
        conf = volcenginesdkcore.Configuration()
        conf.ak = ak
        conf.sk = sk
        conf.region = self._settings.volc_region
        api = volcenginesdkcore.UniversalApi(volcenginesdkcore.ApiClient(conf))
        info = volcenginesdkcore.UniversalInfo(
            method="POST", service=_SERVICE, version=_VERSION,
            action=_ACTION, content_type="application/json",
        )
        body = {
            "PageNumber": 1,
            "PageSize": 100,
            "Filter": {"FoundationModelTag": {"TaskTypes": [_TASK_VQA]}},
            "SortOrder": "Desc",
            "SortBy": "UpdateTime",
        }
        resp = api.do_call(info, body)
        return self._parse(resp)

    @staticmethod
    def _parse(resp: dict) -> list[VisionModel]:
        """从 {Result:{Items:[...]}} 抽出模型项；只保留确含 VQA 能力的，组装可调用 model id。"""
        items = ((resp or {}).get("Result") or {}).get("Items") or []
        models: list[VisionModel] = []
        for it in items:
            name = it.get("Name") or ""
            if not name:
                continue
            tags = it.get("FoundationModelTag") or {}
            if _TASK_VQA not in (tags.get("TaskTypes") or []):
                continue  # 二次校验：服务端筛过仍兜一道，确保确实支持看图
            version = it.get("PrimaryVersion") or ""
            # 推理时按「模型名-主版本」调用（如 doubao-seed-1-6-250615）；用户在前端可再手改兜底
            model_id = f"{name}-{version}" if version else name
            models.append(VisionModel(
                model_id=model_id,
                name=name,
                version=version,
                display_name=it.get("DisplayName") or name,
            ))
        return models
