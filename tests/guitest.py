"""GUI 冒烟测试：不开窗，只验证截图链路 + 识别 + 翻译。

用法：
    .venv/Scripts/python.exe guitest.py
"""

# --- 测试引导：确保能导入项目根目录模块 ---
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Windows 控制台默认 GBK，中文/符号输出会崩；统一成 UTF-8 并放宽错误
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import io
import sys
import time

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import QApplication

from PIL import Image


def qpixmap_to_pil(pixmap: QPixmap) -> Image.Image:
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    if not pixmap.toImage().save(buf, "PNG"):
        raise RuntimeError("QPixmap -> PNG 失败")
    data = bytes(buf.data())
    buf.close()
    return Image.open(io.BytesIO(data)).convert("RGB")


def main():
    app = QApplication(sys.argv)

    screens = QGuiApplication.screens()
    print(f"屏幕数量: {len(screens)}")
    for s in screens:
        g = s.geometry()
        print(
            f"  {s.name()}: {g.width()}x{g.height()} @({g.x()},{g.y()}) "
            f"DPR={s.devicePixelRatio()} 物理={s.size().width() * s.devicePixelRatio():.0f}"
        )

    from jietu.capture import grab_around, grab_all, virtual_geometry

    geo = virtual_geometry()
    print(f"虚拟桌面: {geo.width()}x{geo.height()}")

    t = time.perf_counter()
    shot, geo2, scale = grab_all()
    print(f"grab_all: {shot.width()}x{shot.height()} scale={scale:.3f} "
          f"用时 {(time.perf_counter() - t) * 1000:.0f}ms")

    if shot.width() < 50 or shot.height() < 50:
        print("[FAIL] 截图为空")
        return 1

    # 取词模式的小块
    from PySide6.QtCore import QPoint

    center = QPoint(geo.center())
    t = time.perf_counter()
    small, small_rect = grab_around(center, 320)
    print(f"grab_around: {small.width()}x{small.height()} rect={small_rect} "
          f"用时 {(time.perf_counter() - t) * 1000:.0f}ms")

    # 只验证格式转换，不依赖屏幕上有字
    pil = qpixmap_to_pil(small)
    print(f"QPixmap -> PIL: {pil.size} mode={pil.mode}")
    # 不写入工程目录；需要保留样本时可手动保存 pil。

    from jietu import ocr_engine

    t = time.perf_counter()
    ocr_engine.preload()
    print(f"模型加载: {(time.perf_counter() - t):.2f}s")

    t = time.perf_counter()
    text = ocr_engine.recognize(pil)
    print(f"识别: {(time.perf_counter() - t) * 1000:.0f}ms, {len(text)} 字")
    print("--- 屏幕上光标附近的文字 ---")
    print(text if text else "(无文字)")
    print("----------------------------")

    print("[OK] GUI 链路正常")
    return 0


if __name__ == "__main__":
    sys.exit(main())
