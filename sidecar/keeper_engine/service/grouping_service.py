"""分组（漏斗前的第 0 步）：把相似连拍聚成「瞬间组」。

信号（详见 docs/product-flow.md）：
  - 语义相似：DINOv2 特征余弦相似度（视觉上是不是同一画面）。
  - 时间邻近：EXIF 拍摄时间，越近越可能是同一串连拍（指数衰减）。
  - 人脸身份：两张照片各取「全部主要人脸」的 ArcFace embedding 集合，按双向最近邻匹配的
    平均余弦衡量「是不是同一拨人」——把「同场景、同时间但不同人」拆成不同组（多人合影也适用）。
    两张都有合格人脸时才生效：同一拨人 → 因子≈1（不干预）；不同人 → 因子压到 floor（强制拆开）；
    任一无脸则因子=1（退回纯语义+时间，风景/空镜不受影响）。

综合相似度 = 语义余弦 × 时间衰减 × 人脸因子；距离 = 1 − 综合相似度；complete-linkage 层次聚类按阈值切。
阈值都是可调旋钮，集中在下方常量。
"""

from __future__ import annotations

from collections import OrderedDict
from datetime import datetime
from typing import Sequence

import numpy as np
from fastapi import HTTPException

from ..client.vision_client import VisionClient
from ..exception.errors import VisionUnavailable
from ..request.group_request import GroupRequest
from ..response.common import PhotoError
from ..response.group_response import GroupResponse
from ..util import imaging
from ..vo.group import Group
from .readiness_service import ReadinessService

# ── 可调旋钮 ────────────────────────────────────────────────────────────────
GROUP_DISTANCE_THRESHOLD = 0.4   # 1 − 综合相似度；越小分得越细（同组要求越像）
TIME_TAU_SECONDS = 120.0         # 时间衰减常数：Δt = TAU 时时间因子衰减到 e⁻¹≈0.37
LINKAGE_METHOD = "complete"      # complete-linkage：组内任意两张都要够像，连拍组更紧

# 人脸身份因子：把两张照片人脸集合的相似度（双向最近邻平均余弦）线性映射到 [FACE_FACTOR_FLOOR, 1]。
# 相似度 ≥ SAME 视为同一拨人（因子=1，不干预）；≤ DIFF 视为不同人（因子=floor，强制拆开）。
# floor 足够小，使「同场景不同人」综合相似度被压到 < (1−阈值) 而必被拆。阈值在真实人脸上标定。
FACE_SAME_COS = 0.5              # 人脸集合相似度 ≥ 此值视为同一拨人
FACE_DIFF_COS = 0.2              # 人脸集合相似度 ≤ 此值视为不同人
FACE_FACTOR_FLOOR = 0.1          # 不同人时综合相似度的乘法下限（拉大距离、保证拆组）


class GroupingService:
    """分组能力：用注入的 VisionClient 取语义/人脸特征；纯聚类算法为静态方法、便于单测。"""

    def __init__(self, vision: VisionClient, readiness: ReadinessService) -> None:
        self._vision = vision
        self._readiness = readiness

    def group(self, req: GroupRequest) -> GroupResponse:
        """分组端点编排：就绪门禁 → 逐张取特征（单张失败记 errors）→ 聚类 → 组装响应。"""
        if self._readiness.status != "ready":
            raise HTTPException(
                status_code=503,
                detail=f"模型未就绪（{self._readiness.status}）：{self._readiness.detail or '预热中，请稍后重试'}",
            )
        paths, embeddings, face_sets, times = [], [], [], []
        errors: list[PhotoError] = []
        for p in req.photos:
            try:
                emb, faces, t = self.embed_photo(p)
                paths.append(p)
                embeddings.append(emb)
                face_sets.append(faces)
                times.append(t)
            except VisionUnavailable as e:
                raise HTTPException(status_code=503, detail=f"本地模型不可用：{e}") from e
            except Exception as e:  # noqa: BLE001 —— 单张数据错误上报而非静默跳过
                errors.append(PhotoError(path=p, error=f"{type(e).__name__}: {e}"))

        groups = self.cluster(paths, embeddings, times, face_sets)
        return GroupResponse(groups=groups, errors=errors)

    def embed_photo(
        self, path: str, companions: Sequence[str] = ()
    ) -> tuple[np.ndarray, np.ndarray | None, datetime | None]:
        """加载一张图，返回 (DINOv2 归一特征, 人脸身份集合 (k×d) 或 None, 拍摄时间)。读图/推理失败抛异常。"""
        img = imaging.load_for_analysis(path, tuple(companions))
        return self._vision.embed_image(img), self._vision.face_embeddings(img), imaging.read_capture_time(img)

    @staticmethod
    def _set_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """两张照片人脸集合的相似度：双向最近邻匹配余弦的平均（a、b 均为 k×d 已归一矩阵）。

        对 a 中每张脸取它在 b 中的最佳匹配余弦、求均值（反向同理），再取两方向平均——
        同一拨人双向都能配上 → 接近 1；人群不同 → 接近 0。
        """
        cos = np.clip(a @ b.T, -1.0, 1.0)  # (ka×kb) 成对余弦
        a_to_b = float(cos.max(axis=1).mean())  # a 每张脸的最佳匹配，平均
        b_to_a = float(cos.max(axis=0).mean())
        return (a_to_b + b_to_a) / 2.0

    @staticmethod
    def _face_factor_matrix(face_sets: Sequence[np.ndarray | None]) -> np.ndarray:
        """人脸集合的成对乘法因子矩阵（n×n）：同一拨人≈1、不同人→floor、任一无脸→1。

        face_sets 各元素为某图全部人脸的 (k×d) 已归一矩阵或 None。只有两张都有脸时才按集合
        相似度惩罚，其余处保持 1（缺脸不应惩罚，否则风景/空镜永远聚不到一起）。
        成对（O(n²)）计算：集合相似度无法整体矩阵化，但每对只是两个小矩阵相乘。
        """
        n = len(face_sets)
        span = FACE_SAME_COS - FACE_DIFF_COS
        factor = np.ones((n, n), dtype=np.float64)
        for i in range(n):
            if face_sets[i] is None:
                continue
            for j in range(i + 1, n):
                if face_sets[j] is None:
                    continue
                sim = GroupingService._set_similarity(face_sets[i], face_sets[j])
                f = min(1.0, max(FACE_FACTOR_FLOOR, (sim - FACE_DIFF_COS) / span))
                factor[i, j] = factor[j, i] = f
        return factor

    @staticmethod
    def cluster(
        paths: list[str],
        embeddings: Sequence[np.ndarray],
        times: Sequence[datetime | None],
        face_sets: Sequence[np.ndarray | None] | None = None,
    ) -> list[Group]:
        """把已算好的特征+时间（+可选人脸身份）聚成瞬间组（纯函数，不碰 IO/模型，便于单测）。

        embeddings 须为 L2 归一化向量（点积即余弦）。face_sets 为各图人脸身份集合 (k×d) 矩阵（无脸为 None）；
        传 None 表示全部不参与人脸约束，退回纯「语义×时间」。返回的 Group 按首次出现顺序编号 g1、g2…。
        """
        n = len(paths)
        if n == 0:
            return []
        if n == 1:
            return [Group(id="g1", photos=[paths[0]])]

        e = np.stack(embeddings).astype(np.float32)
        sem = np.clip(e @ e.T, -1.0, 1.0)  # 余弦相似度矩阵

        secs = np.array([t.timestamp() if t is not None else np.nan for t in times], dtype=np.float64)
        dt = np.abs(secs[:, None] - secs[None, :])
        time_factor = np.exp(-dt / TIME_TAU_SECONDS)
        time_factor[np.isnan(time_factor)] = 1.0  # 任一方无时间 → 不衰减，只靠语义

        face_factor = GroupingService._face_factor_matrix(
            face_sets if face_sets is not None else [None] * n
        )

        dist = 1.0 - sem * time_factor * face_factor
        np.fill_diagonal(dist, 0.0)
        dist = np.clip((dist + dist.T) / 2.0, 0.0, None)  # 对称化、非负

        from scipy.cluster.hierarchy import fcluster, linkage
        from scipy.spatial.distance import squareform

        z = linkage(squareform(dist, checks=False), method=LINKAGE_METHOD)
        labels = fcluster(z, t=GROUP_DISTANCE_THRESHOLD, criterion="distance")

        members: OrderedDict[int, list[int]] = OrderedDict()
        for idx, lab in enumerate(labels):
            members.setdefault(int(lab), []).append(idx)
        ordered = sorted(members.values(), key=lambda idxs: idxs[0])  # 按首次出现排序
        return [
            Group(id=f"g{k + 1}", photos=[paths[i] for i in idxs])
            for k, idxs in enumerate(ordered)
        ]
