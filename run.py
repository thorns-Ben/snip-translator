"""启动入口：先做环境检查，异常时弹窗而不是静默退出。

pythonw.exe 没有控制台，未捕获异常会让程序直接消失。
这个入口把所有启动期异常写日志 + 弹 MessageBox，
用户至少能看到"哪里出错了"。
"""

import os
import sys
import traceback
from pathlib import Path

DATA_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "JietuScreenshot"
LOG_PATH = DATA_DIR / "startup_error.log"


def _fatal(msg: str) -> None:
    """弹窗 + 写日志，然后退出。"""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        LOG_PATH.write_text(msg, encoding="utf-8")
    except Exception:
        pass

    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            None, msg[:1500], "截图识字 - 启动失败", 0x10
        )
    except Exception:
        pass

    # 有控制台时也打出来
    try:
        print(msg)
    except Exception:
        pass
    sys.exit(1)


def _self_test() -> None:
    """发布包本地自检，不联网、不写启动项、不加载用户密钥。"""
    import json
    from PIL import Image, ImageDraw, ImageFont
    import onnxruntime
    from PySide6.QtWidgets import QApplication
    from jietu import ocr_engine
    from jietu.capture import CaptureOverlay, MODE_SNIP
    from jietu.settings_dialog import SettingsDialog
    from jietu import autostart

    app = QApplication([])
    image = Image.new("RGB", (720, 100), "white")
    draw = ImageDraw.Draw(image)
    draw.text((15, 15), "Python return file_path 123", fill="black",
              font=ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 28))
    text = ocr_engine.recognize(image)
    assert "Python" in text and "123" in text, text
    assert "返回" in ocr_engine.translate("return", mode="programmer")
    overlay = CaptureOverlay(mode=MODE_SNIP)
    assert not overlay._shot.isNull()
    overlay.close_all()
    assert SettingsDialog is not None and callable(autostart.is_enabled)
    result = {"ok": True, "ocr_text": text,
              "providers": onnxruntime.get_available_providers(),
              "frozen": bool(getattr(sys, "frozen", False))}
    (DATA_DIR / "self-test.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    app.quit()


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if sys.stdout is None or sys.stderr is None:
        log = open(DATA_DIR / "application.log", "a", encoding="utf-8", buffering=1)
        if sys.stdout is None:
            sys.stdout = log
        if sys.stderr is None:
            sys.stderr = log
    base = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    os.chdir(base)

    if "--self-test" in sys.argv:
        _self_test()
        return

    try:
        import PySide6  # noqa: F401
        import rapidocr_onnxruntime  # noqa: F401
    except ImportError as exc:
        _fatal(
            f"依赖缺失: {exc}\n\n"
            f"请先运行 install.bat，或手动执行:\n"
            f'  "{sys.executable}" -m pip install -r requirements.txt\n\n'
            f"当前解释器: {sys.executable}"
        )
        return

    try:
        from jietu import main as app_main
    except Exception:
        _fatal("导入模块失败:\n\n" + traceback.format_exc())
        return

    try:
        app_main.main()
    except SystemExit:
        raise
    except Exception:
        _fatal("运行期异常:\n\n" + traceback.format_exc())


if __name__ == "__main__":
    main()
