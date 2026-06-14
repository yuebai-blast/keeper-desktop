"""请求/响应共用的小结构。"""

from __future__ import annotations

from pydantic import BaseModel


class PhotoError(BaseModel):
    """单张照片处理失败（数据问题，如文件损坏）——上报而非静默跳过。"""

    path: str
    error: str
