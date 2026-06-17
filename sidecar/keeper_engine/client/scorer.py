"""层②（在线 LLM 漏斗）：大模型对候选打 0–100 分。

Scorer 抽象是全系统唯一会演化（本地直调 → 云端中转）的环节：
  - LocalDirectScorer（本版）：sidecar 直连大模型 API（火山 Ark，OpenAI 兼容协议）。
  - CloudRelayScorer（未来商业版）：改调自建云端中转层（鉴权 + 计量计费 + 加价）。
业务流程只依赖 Scorer 协议；商业化时新增实现 + 在 DI 容器里换一行绑定即可，编排逻辑零改动。

照片不出本地：只上传低清预览（Preview.jpeg 字节），绝不传原图；推理完即焚。
"""

from __future__ import annotations

import base64
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from volcenginesdkarkruntime import Ark

from ..config.settings import Settings
from ..enumeration.edit_verdict import EditVerdict
from ..exception.errors import ScorerError
from ..vo.score import Score

# prompt 抽到独立的 prompts/ 文件夹，便于不改代码地迭代提示词
_PROMPTS_DIR = Path(__file__).parent / "prompts"


@lru_cache(maxsize=None)
def _layer2_prompt() -> str:
    """层② 打分提示词（找缺陷 + 锚定分数区间，强制拉开差距）。"""
    return (_PROMPTS_DIR / "layer2_score.md").read_text(encoding="utf-8")


@dataclass
class Preview:
    """送去打分的低清预览：path 仅作身份标识，jpeg 是唯一上传的字节（用完即焚）。"""

    path: str
    jpeg: bytes


class Scorer(Protocol):
    """给一组候选预览打 0–100 分，返回与输入同序的 Score。model 为本次使用的大模型 id。"""

    def score(self, previews: list[Preview], model: str) -> list[Score]:
        ...


def extract_output_text(resp) -> str:
    """从 Responses API 结果里拼出助手文本：遍历 output 的 message 项、取其 output_text 内容。

    Responses API 的 resp.output 是混合列表（可能含 reasoning 等非消息项），且本 SDK 无 output_text
    便捷属性，故显式只取 type=="message" 项里 type=="output_text" 的 text，跳过其余块。
    """
    parts: list[str] = []
    for item in resp.output or []:
        if getattr(item, "type", None) != "message":
            continue
        for content in getattr(item, "content", None) or []:
            if getattr(content, "type", None) == "output_text":
                parts.append(content.text)
    return "".join(parts)


def parse_response(text: str) -> tuple[float, str, str, str, str]:
    """从大模型回复抽出 {"score","reason","flaws","editable","edit_advice"}：
    score clamp 0–100，reason/flaws/edit_advice 截断，editable 落到合法四态（非法兜底 ready）。解析失败抛异常。"""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError(f"无法从打分输出解析 JSON：{text!r}")
    data = json.loads(m.group(0))
    score = max(0.0, min(100.0, float(data["score"])))
    reason = str(data.get("reason", "")).strip()[:30]
    flaws = str(data.get("flaws", "")).strip()[:100]
    editable = EditVerdict.coerce(data.get("editable"))
    edit_advice = str(data.get("edit_advice", "")).strip()[:40]
    return round(score, 2), reason, flaws, editable, edit_advice


class LocalDirectScorer:
    """本版实现：sidecar 直连火山 Ark（OpenAI 兼容）。构造注入 Settings；model 在调用时传。

    商业版换 CloudRelayScorer 指向自建中转，业务流程不变（只改 DI 容器绑定）。
    """

    def __init__(self, settings: Settings, api_key: str | None = None) -> None:
        self._settings = settings
        self._api_key = api_key  # None 时从 env / settings.ark_key_file 解析

    def _load_api_key(self) -> str:
        if self._api_key:
            return self._api_key
        env = os.environ.get("ARK_API_KEY")
        if env:
            return env.strip()
        key_file = self._settings.ark_key_file
        if key_file.exists():
            return key_file.read_text(encoding="utf-8").strip()
        raise ScorerError(f"未找到 Ark API key（设环境变量 ARK_API_KEY 或写入 {key_file}）")

    def _client(self, model: str) -> Ark:
        if not model:
            raise ScorerError("未指定 Ark 模型 id（请求字段 model 或环境变量 KEEPER_ARK_MODEL）")
        return Ark(api_key=self._load_api_key(), base_url=self._settings.ark_base_url)

    def score(self, previews: list[Preview], model: str) -> list[Score]:
        if not previews:
            return []
        client = self._client(model)
        workers = max(1, min(self._settings.ark_concurrency, len(previews)))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            return list(ex.map(lambda p: self._score_one(client, model, p), previews))

    def _score_one(self, client: Ark, model: str, preview: Preview) -> Score:
        # 内存低清预览直接 base64 拼成 data URL（火山 Ark「Base64 编码传入」）；照片不出本地、用完即焚。
        data_url = "data:image/jpeg;base64," + base64.b64encode(preview.jpeg).decode("ascii")
        last_err: Exception | None = None
        for _ in range(2):  # 失败重试一次
            try:
                resp = client.responses.create(
                    model=model,
                    input=[
                        {"role": "user", "content": [
                            {"type": "input_text", "text": _layer2_prompt()},
                            {"type": "input_image", "image_url": data_url},
                        ]}
                    ],
                    temperature=0.0,
                    max_output_tokens=400,
                    # 打分提示词要求「只输出 JSON」，无需思维链；且 max_output_tokens 含思维链，
                    # 开思考会吃掉回答预算导致 JSON 截断，故显式关闭（见火山 Response 文档）。
                    thinking={"type": "disabled"},
                )
                score, reason, flaws, editable, edit_advice = parse_response(extract_output_text(resp))
                return Score(
                    path=preview.path, score=score, reason=reason, flaws=flaws,
                    editable=editable, edit_advice=edit_advice,
                )
            except Exception as e:  # noqa: BLE001 —— 重试后仍失败则包装上抛
                last_err = e
        raise ScorerError(f"{Path(preview.path).name} 打分失败：{last_err}") from last_err
