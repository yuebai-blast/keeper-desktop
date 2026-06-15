"""workspace 文件操作：扫描源文件夹、复制副本、最终归档、清理。

两类复制走这里：
  ① 导入时把源图（递归）复制到 ~/.keeper/workspace/{name}，并改名成随机 UUID——
     工作期文件名不重要，扁平 + UUID 彻底回避跨子目录重名 / 同 stem 异扩展名的冲突。
  ② 完成时把「通过」的副本按相对路径**还原原始目录树 + 原始文件名**到 ~/Pictures/Keeper/{name}。
复制保留元数据（copy2）。只动 workspace 副本与输出目录，绝不写用户源文件夹（照片不出本地、不改原图）。
"""

from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

from ..util.imaging import ALL_INPUT_EXTS

_THUMB_DIRNAME = ".thumbnails"  # 缩略图缓存子目录名，扫描时跳过


class WorkspaceService:
    """文件扫描 / 复制 / 删除（纯文件系统操作，无状态）。"""

    @staticmethod
    def scan_images(folder: str) -> list[Path]:
        """递归列出文件夹内的图片文件（按相对路径排序）。目录不存在抛异常。

        递归覆盖子文件夹（按日期/场景/机位组织的工程常见）；跳过缩略图缓存目录。
        """
        base = Path(folder)
        if not base.is_dir():
            raise NotADirectoryError(f"不是有效目录：{folder}")
        files = [
            p for p in base.rglob("*")
            if p.is_file()
            and p.suffix.lower() in ALL_INPUT_EXTS
            and _THUMB_DIRNAME not in p.parts
        ]
        return sorted(files, key=lambda p: p.relative_to(base).as_posix())

    @staticmethod
    def copy_into(paths: list[str], dest_dir: str) -> list[tuple[str, str]]:
        """把 paths 逐个复制到 dest_dir，改名成 `{uuid}{原扩展名}`，返回 [(源, 目标)] 映射。

        UUID 保证目标唯一，无需重名避让。单张复制失败抛异常给调用方（导入需整体可靠）。
        """
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        mapping: list[tuple[str, str]] = []
        for src in paths:
            target = dest / f"{uuid4().hex}{Path(src).suffix.lower()}"
            shutil.copy2(src, target)
            mapping.append((src, str(target)))
        return mapping

    @staticmethod
    def restore_tree(items: list[tuple[str, str]], dest_root: str) -> list[str]:
        """把 [(副本绝对路径, 相对路径)] 按相对路径还原到 dest_root 下（重建目录树 + 原始名）。

        相对路径取自源树的子集、天然唯一，不会重名。返回实际写出的目标路径列表。
        """
        root = Path(dest_root)
        out: list[str] = []
        for src, rel in items:
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
            out.append(str(target))
        return out

    @staticmethod
    def remove_dir(path: str) -> None:
        """删除整个目录（best-effort，用于完成后回收 workspace 空间）。"""
        shutil.rmtree(path, ignore_errors=True)
