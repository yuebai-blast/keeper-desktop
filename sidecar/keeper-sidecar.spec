# PyInstaller 配置：把 Keeper sidecar 冻结成「单文件」可执行（Tauri sidecar 机制需单个二进制）。
# torch / onnxruntime / pyiqa / insightface / rawpy / opencv 等需 collect 全部子模块与数据文件。
# 模型权重不打包，运行时下载到 ~/.keeper/models。
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas, binaries, hiddenimports = [], [], []
for pkg in ("torch", "torchvision", "onnxruntime", "insightface", "pyiqa",
            "timm", "cv2", "rawpy", "pillow_heif", "transformers",
            # clip（openai-clip）按 __file__ 相对路径加载词表
            # bpe_simple_vocab_16e6.txt.gz，属非 .py 数据文件，
            # PyInstaller 静态分析收不到，需 collect_all 带上其 datas，
            # 否则 pyiqa 的 CLIP-IQA+ 打包后会缺词表报 FileNotFoundError。
            "clip",
            # dependency_injector 是 Cython 扩展，其内部子模块（errors 等）
            # PyInstaller 静态分析探测不到，需显式 collect 全部子模块。
            "dependency_injector"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h
hiddenimports += collect_submodules("uvicorn")

a = Analysis(
    ["entry.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="keeper-sidecar",
    console=True,
    onefile=True,
)
