# PyInstaller 配置：把 Keeper sidecar 冻结成「单目录」（onedir）——一个含可执行 + _internal/ 的目录。
# 不用 onefile：onefile 每次启动都把整包自解压到临时目录（实测 ~24s，且每次都付），首装还叠加
# 未公证大二进制的 Gatekeeper 全盘扫描，放大成几分钟。onedir 库直接躺在包里，去掉自解压、二次启动近秒开；
# 且产物是真实目录，构建完即可 `ls _internal/` 核对数据文件是否漏收（onefile 是不透明 blob、装机才崩）。
# Tauri 侧不再走 externalBin（只认单文件），改由 bundle.resources 整目录随包 + Rust 从 resource 路径拉起。
# torch / onnxruntime / pyiqa / insightface / rawpy / opencv 等需 collect 全部子模块与数据文件。
# 模型权重不打包，运行时下载到 ~/.keeper/models。
import os
from glob import glob

from PyInstaller.utils.hooks import collect_all, collect_submodules

datas, binaries, hiddenimports = [], [], []
# keeper_engine 自身被 PyInstaller 当源码静态收集，只带 .py；包内的非 .py 数据文件
# （如 client/prompts/layer2_score.md 提示词）收不到，装机后 read_text 会 FileNotFoundError。
# 这里按磁盘路径显式收本包所有非 .py 数据文件（不用 collect_data_files：执行 spec 时
# keeper_engine 不在 import 路径上，它会静默返回空）。SPECPATH=spec 所在目录=sidecar。
# 每个文件按其相对 keeper_engine 的子目录回放，原包内相对路径不变；将来新增数据文件自动覆盖。
for _src in glob(os.path.join(SPECPATH, "keeper_engine", "**", "*"), recursive=True):
    if os.path.isfile(_src) and not _src.endswith((".py", ".pyc")):
        datas.append((_src, os.path.dirname(os.path.relpath(_src, SPECPATH))))
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
# onedir：EXE 只放引导器（exclude_binaries=True 把库剔出 exe），库与数据文件交给 COLLECT 落到目录。
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="keeper-sidecar",
    console=True,
)
# COLLECT 产出目录 dist/keeper-sidecar/（内含 keeper-sidecar 可执行 + _internal/ 全部库与数据）。
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="keeper-sidecar",
)
