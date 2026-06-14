"""本地模型客户端（线程安全懒加载）——层① / 分组用到的模型都在这里。

含：
  - DINOv2（语义特征）：分组用，embed_image 出归一向量做视觉相似聚类。
    选 v2 不选 v3：v2 是 Apache-2.0、HF 免门禁、自动下载即用、商用干净；v3 是 gated + 自定义许可。
  - InsightFace：层① 加载「检测 + 68 关键点」（算锐度/闭眼），不载识别模型；
    分组另用「检测 + 识别」实例取人脸身份 embedding，把「同场景不同人」拆成不同组。
    ⚠️ 识别模型（ArcFace，buffalo_l）仅限非商用研究——付费产品商用前需替换或单独授权。
  - pyiqa：TOPIQ-nr-face（有脸时评人脸质量）/ TOPIQ-nr（无脸时评整图）+ CLIP-IQA+（美学）。

设计：
  - 实例持有模型缓存（DI 容器以 Singleton 注入，全局一份）；构造参数 settings 提供配置。
  - 模型缓存统一固定到 settings.models_dir（HF / torch / insightface），可复现、不污染全局。
  - 缺依赖或模型加载失败立刻抛 VisionUnavailable——不静默降级（CLAUDE.md）。
  - 设备：默认 CPU（桌面端最稳）；settings.device=cuda 时用 CUDA。pyiqa 在 MPS 上易炸，固定不走 MPS。
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import numpy as np
from PIL import Image

from ..config.settings import Settings
from ..exception.errors import VisionUnavailable
from ..util import signals

logger = logging.getLogger("keeper_engine.client.vision")

PYIQA_MAX_SIDE = 1024  # pyiqa 输入长边上限，平衡精度与开销

# 层① 只需检测 + 68 关键点（算锐度/闭眼），不加载识别模型：层①用不到，加载更快、内存更省。
DETECT_MODULES = ("detection", "landmark_3d_68")

# 分组用：检测 + 识别（ArcFace），取人脸身份 embedding 区分「同场景不同人」。
# 与 DETECT_MODULES 是两个独立缓存实例（modules 不同）；识别需要 detection 输出的 5 点 kps 做对齐，
# 不需要 68 关键点，故不含 landmark。⚠️ 识别模型仅限非商用研究，商用前需替换或授权（见模块 docstring）。
GROUPING_FACE_MODULES = ("detection", "recognition")
GROUPING_FACE_DET_MIN = 0.5     # 人脸最低检测置信度（低于此当背景误检，不取其身份）
GROUPING_FACE_MIN_AREA = 0.005  # 人脸面积占比下限（过滤背景路人小脸，只留画面里的主要人物）


class VisionClient:
    """本地推理模型的统一入口；构造注入 Settings，实例内线程安全懒加载并缓存各模型。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._lock = threading.Lock()
        self._models: dict = {}
        self._storage_ready = False

    # ── 存储 / 设备 ────────────────────────────────────────────────────────

    def _models_root(self) -> Path:
        root = self._settings.models_dir
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _ensure_storage_configured(self) -> None:
        """把各框架的缓存目录指到 Keeper 自己的目录。必须在 import/加载模型前设置。"""
        if self._storage_ready:
            return
        with self._lock:
            if self._storage_ready:
                return
            import os

            root = self._models_root()
            hf_home = root / "huggingface"
            hf_hub = hf_home / "hub"
            torch_home = root / "torch"
            for p in (hf_home, hf_hub, torch_home, root / "insightface"):
                p.mkdir(parents=True, exist_ok=True)
            os.environ.setdefault("HF_HOME", str(hf_home))
            os.environ.setdefault("HF_HUB_CACHE", str(hf_hub))
            os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(hf_hub))
            os.environ.setdefault("TORCH_HOME", str(torch_home))
            try:
                import torch.hub

                torch.hub.set_dir(str(torch_home / "hub"))
            except Exception:
                pass
            self._storage_ready = True
            logger.info("vision: 模型缓存目录固定到 %s", root)

    def _torch_device(self):
        import torch

        forced = self._settings.device
        if forced == "cuda":
            if not torch.cuda.is_available():
                raise VisionUnavailable("KEEPER_DEVICE=cuda，但 torch 不支持 CUDA")
            return torch.device("cuda")
        if forced == "cpu" or not forced:
            if forced == "" and torch.cuda.is_available():
                return torch.device("cuda")
            return torch.device("cpu")
        return torch.device("cpu")

    # ── DINOv2：语义特征（分组用）──────────────────────────────────────────

    def _ensure_dinov2(self):
        self._ensure_storage_configured()
        if "dinov2" in self._models:
            return self._models["dinov2"]
        with self._lock:
            if "dinov2" in self._models:
                return self._models["dinov2"]
            try:
                import torch  # noqa: F401
                from transformers import AutoImageProcessor, AutoModel
            except ImportError as e:
                raise VisionUnavailable(f"DINOv2 依赖缺失：{e}（需 transformers + torch）") from e
            model_id = self._settings.dino_model
            dev = self._torch_device()
            logger.info("vision: 加载 DINOv2 %s（device=%s，首次需下载权重）…", model_id, dev.type)
            try:
                proc = AutoImageProcessor.from_pretrained(model_id)
                model = AutoModel.from_pretrained(model_id).to(dev).eval()
            except Exception as e:
                raise VisionUnavailable(f"DINOv2 加载失败：{e}") from e
            self._models["dinov2"] = (proc, model, dev)
            logger.info("vision: DINOv2 就绪")
        return self._models["dinov2"]

    def embed_image(self, img: Image.Image) -> np.ndarray:
        """返回一张图的 DINOv2 语义特征（L2 归一化的 float32 向量）。

        归一后两向量点积即余弦相似度——分组用它衡量「视觉上是不是同一画面」。
        """
        import torch

        proc, model, dev = self._ensure_dinov2()
        inputs = proc(images=img.convert("RGB"), return_tensors="pt").to(dev)
        with torch.no_grad():
            out = model(**inputs)
        pooled = getattr(out, "pooler_output", None)
        feat = pooled[0] if pooled is not None else out.last_hidden_state[0, 0]
        v = feat.detach().cpu().numpy().astype(np.float32)
        n = float(np.linalg.norm(v))
        return v / n if n >= 1e-8 else v

    # ── pyiqa：TOPIQ-nr（技术质量）+ CLIP-IQA+（美学）──────────────────────

    @staticmethod
    def _resize_for_pyiqa(img: Image.Image) -> Image.Image:
        img = img.convert("RGB")
        if max(img.size) <= PYIQA_MAX_SIDE:
            return img
        out = img.copy()
        out.thumbnail((PYIQA_MAX_SIDE, PYIQA_MAX_SIDE), Image.Resampling.LANCZOS)
        return out

    def _ensure_pyiqa(self, key: str, metric_name: str, label: str):
        self._ensure_storage_configured()
        if key in self._models:
            return self._models[key]
        with self._lock:
            if key in self._models:
                return self._models[key]
            try:
                import pyiqa  # noqa: F401
                import torch  # noqa: F401
            except ImportError as e:
                raise VisionUnavailable(f"{label} 依赖缺失：{e}（需 pyiqa + timm）") from e
            dev = self._torch_device()
            logger.info("vision: 加载 %s（%s, device=%s，首次需下载权重）…", label, metric_name, dev.type)
            try:
                model = pyiqa.create_metric(metric_name, device=dev, as_loss=False)
            except Exception as e:
                raise VisionUnavailable(f"{label} 加载失败：{e}") from e
            self._models[key] = model
            logger.info("vision: %s 就绪", label)
        return self._models[key]

    def _pyiqa_score(self, key: str, metric_name: str, label: str, img: Image.Image) -> float:
        import torch

        model = self._ensure_pyiqa(key, metric_name, label)
        with torch.no_grad():
            score = model(self._resize_for_pyiqa(img))
        return float(score.item() if hasattr(score, "item") else score)

    def topiq_score(self, img: Image.Image) -> float:
        """TOPIQ-nr 通用技术质量分（约 0–1，越高越好）。用于无脸照（风景/空镜）。"""
        return self._pyiqa_score("topiq", "topiq_nr", "TOPIQ-nr", img)

    def topiq_face_score(self, face_img: Image.Image) -> float:
        """TOPIQ-nr-face 人脸质量分（GFIQA 训练，约 0–1，越高越好）。

        专为人脸场景设计，输入应为人脸裁剪。人像选片用它比通用 topiq_nr 更贴合。
        """
        return self._pyiqa_score("topiq_face", "topiq_nr-face", "TOPIQ-nr-face", face_img)

    def clipiqa_plus_score(self, img: Image.Image) -> float:
        """CLIP-IQA+ 美学分（约 0–1，越高越好）。"""
        return self._pyiqa_score("clipiqa", "clipiqa+", "CLIP-IQA+", img)

    # ── InsightFace：检测 + 嵌入 + 关键点 ─────────────────────────────────

    def _onnx_providers(self) -> tuple[list[str], int]:
        import onnxruntime as ort

        forced = self._settings.device
        available = list(ort.get_available_providers())
        if forced == "cuda" or (forced == "" and "CUDAExecutionProvider" in available):
            if "CUDAExecutionProvider" in available:
                return ["CUDAExecutionProvider", "CPUExecutionProvider"], 0
        return ["CPUExecutionProvider"], -1

    def _ensure_insightface(self, modules: tuple[str, ...] = DETECT_MODULES):
        self._ensure_storage_configured()
        key = "insightface:" + ",".join(sorted(modules))
        if key in self._models:
            return self._models[key]
        with self._lock:
            if key in self._models:
                return self._models[key]
            try:
                from insightface.app import FaceAnalysis
            except ImportError as e:
                raise VisionUnavailable(f"InsightFace 依赖缺失：{e}（需 insightface + onnxruntime）") from e
            providers, ctx_id = self._onnx_providers()
            pack = self._settings.face_pack
            root = str(self._models_root() / "insightface")
            logger.info("vision: 加载 InsightFace %s modules=%s（providers=%s）…", pack, modules, providers)
            try:
                app = FaceAnalysis(name=pack, root=root, providers=providers, allowed_modules=list(modules))
                app.prepare(ctx_id=ctx_id, det_size=(640, 640))
            except Exception as e:
                raise VisionUnavailable(f"InsightFace 加载失败：{e}") from e
            self._models[key] = app
            logger.info("vision: InsightFace 就绪（%s）", key)
        return self._models[key]

    def extract_faces(
        self, img: Image.Image, max_dim: int = 1024, modules: tuple[str, ...] = DETECT_MODULES
    ) -> list[dict]:
        """返回每张脸的 {bbox(x1,y1,x2,y2,原图坐标), embedding(512d 已归一 or None),
        kps, det_score, landmark_2d_68}。无脸返回 []，依赖问题抛 VisionUnavailable。

        embedding 仅在 modules 含 "recognition" 时才有值（层① 默认不加载识别模型，故为 None）。
        """
        app = self._ensure_insightface(modules)
        rgb = img.convert("RGB")
        w, h = rgb.size
        scale = 1.0
        if max(w, h) > max_dim:
            scale = max_dim / max(w, h)
            rgb = rgb.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

        arr = np.array(rgb)[:, :, ::-1]  # RGB → BGR
        faces = app.get(arr)
        if not faces:
            return []

        inv = 1.0 / scale
        out: list[dict] = []
        for face in faces:
            embedding = None
            emb = getattr(face, "embedding", None)
            if emb is not None:
                emb = emb.astype(np.float32)
                n = float(np.linalg.norm(emb))
                if n >= 1e-8:
                    embedding = emb / n
            bbox = tuple(int(c * inv) for c in face.bbox.astype(int))
            kps = (face.kps * inv).astype(np.float32) if face.kps is not None else None
            lm68 = None
            lm = getattr(face, "landmark_3d_68", None)
            if lm is not None:
                lm68 = (lm[:, :2] * inv).astype(np.float32)
            out.append({
                "bbox": bbox,
                "embedding": embedding,
                "kps": kps,
                "det_score": float(face.det_score),
                "landmark_2d_68": lm68,
            })
        return out

    def face_embeddings(self, img: Image.Image) -> np.ndarray | None:
        """取一张照片中所有合格人脸（置信度够、面积够大）的身份 embedding，堆叠成 (k×512) 已归一矩阵。

        供分组按「人群」区分：保留全部主要人脸（非只主脸），多人合影也能比对是不是同一拨人。
        无合格人脸时返回 None——分组遇 None 即不参与人脸约束，只靠语义+时间。
        用含 "recognition" 的独立实例，依赖问题照常抛 VisionUnavailable（不静默降级）。
        """
        faces = self.extract_faces(img, modules=GROUPING_FACE_MODULES)
        w, h = img.size
        area = float(w * h) or 1.0
        embs = []
        for f in faces:
            if f["det_score"] < GROUPING_FACE_DET_MIN or f.get("embedding") is None:
                continue
            x1, y1, x2, y2 = f["bbox"]
            if max(0.0, x2 - x1) * max(0.0, y2 - y1) / area < GROUPING_FACE_MIN_AREA:
                continue
            embs.append(f["embedding"])
        return np.stack(embs).astype(np.float32) if embs else None

    @staticmethod
    def eye_open_score(face: dict) -> float | None:
        """68 关键点估算睁眼程度（EAR 均值）。睁眼 0.25+，闭眼 <0.2。

        点序异常（EAR>0.55，InsightFace 某些角度会输出离谱值）时返回 None，
        让上层按「未知」处理，避免把坏数据当成「睁得很开」放过真闭眼。
        """
        lm68 = face.get("landmark_2d_68")
        if lm68 is None or len(lm68) < 48:
            return None
        lm68 = np.asarray(lm68, dtype=np.float32)
        val = (signals.ear(lm68[36:42]) + signals.ear(lm68[42:48])) / 2.0
        if val > 0.55:
            return None
        return round(val, 4)

    # ── 能力校验 ──────────────────────────────────────────────────────────

    def require_layer1_capabilities(self) -> None:
        """层① 所需模型全部能加载，否则抛异常（启动期 / 首次调用前可主动校验）。"""
        self._ensure_insightface()
        self._ensure_pyiqa("topiq", "topiq_nr", "TOPIQ-nr")
        self._ensure_pyiqa("topiq_face", "topiq_nr-face", "TOPIQ-nr-face")
        self._ensure_pyiqa("clipiqa", "clipiqa+", "CLIP-IQA+")

    def require_grouping_capabilities(self) -> None:
        """分组所需模型能加载，否则抛异常。DINOv2（语义）+ InsightFace 检测/识别（人脸身份）。"""
        self._ensure_dinov2()
        self._ensure_insightface(GROUPING_FACE_MODULES)
