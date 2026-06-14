"""缩略图端点：sidecar 解码（含 RAW/HEIC）并缩放，带磁盘缓存。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from ..util import imaging

router = APIRouter()


@router.get("/thumbnail")
def thumbnail(
    path: str = Query(..., description="照片绝对路径"),
    size: int = Query(256, ge=32, le=1024, description="缩略图长边像素"),
) -> Response:
    """生成并返回一张照片的缩略图 JPEG（桌面端画廊用）。

    sidecar 能解 RAW/HEIC 并缩放（webview 做不到）；只走 localhost，照片不出本地。
    带磁盘缓存（原图改动自动失效）。读图失败 → 404。
    """
    try:
        jpeg = imaging.cached_thumbnail(path, max_side=size)
    except Exception as e:  # noqa: BLE001 —— 路径无效/损坏当 404
        raise HTTPException(status_code=404, detail=f"{type(e).__name__}: {e}") from e
    return Response(content=jpeg, media_type="image/jpeg", headers={"Cache-Control": "max-age=3600"})
