"""截图保存路径与文件名。"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtGui import QPixmap


def app_data_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "JietuScreenshot"


def default_save_dir() -> Path:
    override = os.environ.get("JIETU_SAVE_DIR")
    if override:
        return Path(override).expanduser()
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parent.parent
    return base / "Screenshots"


def ensure_dir(path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def unique_png_path(directory) -> Path:
    d = ensure_dir(directory)
    base = "Snipaste_" + datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = d / f"{base}.png"
    n = 1
    while path.exists():
        path = d / f"{base}_{n}.png"
        n += 1
    return path


def save_pixmap(pixmap: QPixmap, path) -> Path:
    p = Path(path)
    ensure_dir(p.parent)
    if not pixmap.save(str(p), "PNG"):
        raise OSError(f"写入失败: {p}")
    return p
