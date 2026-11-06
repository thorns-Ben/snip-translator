"""截图识字 —— 全局热键 -> 框选 -> OCR -> 翻译，一步到位。

热键：
  F1       截图标注（Snipaste 式：标注 / 复制图片 / 保存 / 贴图，不识别）
  Alt+D    框选区域识别（主功能）
  Alt+Q    整图转文本（当前屏幕整张）
  Alt+Z    取词模式（鼠标所指的小块区域）
  F3       贴图（截图时贴当前选区，平时贴剪贴板）
  Esc      取消框选 / 关闭结果窗
退出：托盘图标右键 -> 退出
"""

import io
import os
import sys
import threading
import time

from PySide6.QtCore import QBuffer, QIODevice, QObject, QPoint, QRect, QSize, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QColor, QCursor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QMenu,
    QMessageBox,
    QSystemTrayIcon,
    QWidget,
)

from . import ocr_engine
from .capture import CaptureOverlay, grab_around, grab_all, MODE_SNIP, MODE_TRANSLATE
from .hotkeys import HotkeyManager
from .paths import default_save_dir, ensure_dir
from .pin_window import PinManager
from .result_window import ResultWindow

HOTKEY_CAPTURE = ("alt+d",)
HOTKEY_FULL = ("alt+q", "alt+shift+q", "ctrl+alt+q")
HOTKEY_HOVER = ("alt+z", "alt+shift+z", "ctrl+alt+z")
HOTKEY_SNIP = ("f1", "alt+1", "ctrl+alt+f1")
HOTKEY_PIN = ("f3", "alt+3", "ctrl+alt+f3")

HK_CAPTURE, HK_FULL, HK_HOVER, HK_SNIP, HK_PIN = 1, 2, 3, 4, 5

HOVER_SIZE = 320  # 取词模式抓取的正方形边长（逻辑像素）


def make_icon() -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor("#e8503a"))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(4, 4, 56, 56, 13, 13)
    p.setPen(QColor("white"))
    f = p.font()
    f.setPixelSize(30)
    f.setBold(True)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignCenter, "文")
    p.end()
    return QIcon(pm)


def qpixmap_to_pil(pixmap: QPixmap):
    from PIL import Image

    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    pixmap.toImage().save(buf, "PNG")
    data = bytes(buf.data())
    buf.close()
    return Image.open(io.BytesIO(data)).convert("RGB")


class OcrResultBridge(QObject):
    """工作线程 -> GUI 线程的桥。

    QTimer.singleShot 在工作线程里创建时归属该线程，
    而线程没有事件循环，回调永远不会执行。必须用信号。
    """

    finished = Signal(str, object, object, int)  # text, error, context, generation


class App(QObject):
    def __init__(self, qapp: QApplication):
        super().__init__()
        self.qapp = qapp
        self.overlay: CaptureOverlay | None = None
        self.window = ResultWindow()
        self.window.hide()

        # 结果窗里的「重新框选 / 整图」按钮回调
        self.window._on_recapture = self.start_capture
        self.window._on_fullimage = self.start_full_image
        self.window.mode_changed = self._on_overlay_mode_changed

        self._busy = False
        self._ocr_generation = 0
        self._capture_mode = MODE_TRANSLATE
        self.programmer_mode = False
        self.hotkeys: HotkeyManager | None = None
        self._hotkey_labels: dict[int, str] = {}

        self.save_dir = ensure_dir(default_save_dir())
        self.pin_manager = PinManager(save_dir=self.save_dir, parent=self)
        self.pin_manager.changed.connect(self._rebuild_pin_menu)

        # 工作线程 -> GUI 线程
        self._ocr_bridge = OcrResultBridge()
        self._ocr_bridge.finished.connect(self._on_ocr_done)

        self._setup_hotkeys()   # 先注册热键，托盘菜单才能显示实际生效的快捷键
        self._build_tray()

        # 提前加载模型，避免第一次截图等太久
        threading.Thread(target=self._preload, daemon=True).start()

    # ---------------------------------------------------- 托盘
    def _build_tray(self):
        self.tray = QSystemTrayIcon(make_icon(), self.qapp)
        tip = "截图识字"
        for hid, name in (
            (HK_SNIP, "截图标注"), (HK_CAPTURE, "框选识别"),
            (HK_FULL, "整图转文本"), (HK_HOVER, "取词模式"),
            (HK_PIN, "贴图"),
        ):
            if hid in self._hotkey_labels:
                tip += f"\n{self._hotkey_labels[hid]}  {name}"
        self.tray.setToolTip(tip)

        menu = QMenu()
        lbl = self._hotkey_labels
        act_snip = QAction(f"截图标注\t{lbl.get(HK_SNIP, '')}", menu)
        act_cap = QAction(f"框选识别\t{lbl.get(HK_CAPTURE, '')}", menu)
        from . import autostart

        self._act_autostart = QAction("开机自启动", menu)
        self._act_autostart.setCheckable(True)
        try:
            self._act_autostart.setChecked(autostart.is_enabled())
        except OSError:
            self._act_autostart.setChecked(False)
        act_settings = QAction("翻译设置", menu)
        act_hover = QAction(f"取词模式\t{lbl.get(HK_HOVER, '')}", menu)
        act_pin_clip = QAction(f"贴图（剪贴板）\t{lbl.get(HK_PIN, '')}", menu)
        act_toggle = QAction("显示/隐藏结果窗", menu)
        act_open_dir = QAction("打开截图文件夹", menu)
        act_quit = QAction("退出", menu)

        act_snip.triggered.connect(lambda: self.start_capture(MODE_SNIP))
        act_cap.triggered.connect(lambda: self.start_capture(MODE_TRANSLATE))
        self._act_autostart.triggered.connect(self._toggle_autostart)
        act_settings.triggered.connect(self._show_settings)
        act_hover.triggered.connect(self.start_hover)
        act_pin_clip.triggered.connect(self.pin_from_clipboard)
        act_toggle.triggered.connect(self._toggle_window)
        act_open_dir.triggered.connect(self._open_save_dir)
        act_quit.triggered.connect(self.quit)

        self._pin_menu = menu.addMenu("贴图")
        self._pin_menu.setStyleSheet(
            "QMenu { background: #2c2f35; color: #d5d9df; border: 1px solid #4a4f58;"
            " padding: 4px; }"
        )

        menu.addAction(act_snip)
        menu.addAction(act_cap)
        menu.addAction(self._act_autostart)
        menu.addAction(act_settings)
        menu.addAction(act_hover)
        menu.addAction(act_pin_clip)
        menu.addSeparator()
        menu.addAction(act_toggle)
        menu.addAction(act_open_dir)
        menu.addSeparator()
        menu.addAction(act_quit)
        menu.setStyleSheet(
            """
            QMenu { background: #2c2f35; color: #d5d9df; border: 1px solid #4a4f58;
                    padding: 4px; }
            QMenu::item { padding: 6px 28px 6px 20px; border-radius: 3px; }
            QMenu::item:selected { background: #e8503a; color: white; }
            QMenu::separator { height: 1px; background: #3f434b; margin: 4px 8px; }
            """
        )
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()
        self._rebuild_pin_menu()

        # 启动提示：否则用户双击后完全没反应，不知道程序在跑
        QTimer.singleShot(600, self._show_startup_tip)

    def _toggle_autostart(self, checked: bool):
        from . import autostart

        try:
            autostart.set_enabled(checked)
        except OSError as exc:
            QMessageBox.warning(None, "开机自启动设置失败", str(exc))
        try:
            self._act_autostart.setChecked(autostart.is_enabled())
        except OSError:
            self._act_autostart.setChecked(False)

    def _show_settings(self):
        from .settings_dialog import SettingsDialog

        dialog = getattr(self, "_settings_dialog", None)
        if dialog is None:
            dialog = SettingsDialog()
            dialog.saved.connect(self._settings_saved)
            self._settings_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _settings_saved(self):
        with ocr_engine._CACHE_LOCK:
            ocr_engine._TRANSLATE_CACHE.clear()
        ocr_engine._PROVIDER_FAIL_UNTIL.clear()
        self._ocr_generation += 1
        self.window._translation_generation += 1
        self.window._translation_pending = False
        self.window.btn_translate.setEnabled(True)
        self.window.status.setText("设置已更新，可重新翻译")
        if self.overlay is not None and self.overlay.mode == MODE_TRANSLATE:
            self.overlay.panel.set_status("设置已更新，可重新识别或翻译")
        self.tray.showMessage("截图识字", "翻译设置已保存，之后的请求使用新配置。",
                              QSystemTrayIcon.Information, 2000)

    def _rebuild_pin_menu(self):
        pin_menu = getattr(self, "_pin_menu", None)
        if pin_menu is None:
            return
        pin_menu.clear()
        pins = self.pin_manager.all()
        if not pins:
            empty = pin_menu.addAction("（没有贴图）")
            empty.setEnabled(False)
            return
        pin_menu.addAction("显示全部", self.pin_manager.show_all)
        pin_menu.addAction("隐藏全部", self.pin_manager.hide_all)
        pin_menu.addAction("取消全部鼠标穿透",
                           lambda: self.pin_manager.set_mouse_through_all(False))
        pin_menu.addAction("关闭全部", self.pin_manager.close_all)
        pin_menu.addSeparator()
        for idx, pin in enumerate(pins, 1):
            size = pin._display.size() if not pin._display.isNull() else QSize()
            w = int(round(size.width() / max(1.0, pin._dpr)))
            h = int(round(size.height() / max(1.0, pin._dpr)))
            act = pin_menu.addAction(f"关闭贴图 {idx}  ({w}×{h})")
            act.triggered.connect(lambda _=False, p=pin: p.close())

    def _open_save_dir(self):
        try:
            os.startfile(str(self.save_dir))
        except Exception:
            pass

    def _show_startup_tip(self):
        keys = "\n".join(
            f"{self._hotkey_labels.get(h, '注册失败，请用托盘菜单')}  {name}"
            for h, name in ((HK_SNIP, "截图标注"), (HK_CAPTURE, "框选翻译"), (HK_PIN, "贴图"))
        )
        self.tray.showMessage(
            "截图识字已启动",
            keys,
            QSystemTrayIcon.Information,
            4000,
        )

    def _on_tray_activated(self, reason):
        # 左键单击或双击都触发框选，Windows 上单击更符合直觉
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.start_capture()

    def _toggle_window(self):
        if self.window.isVisible():
            self.window.hide()
        elif self.window._source:
            self.window.show()
            self.window.raise_()
            self.window.activateWindow()

    # ---------------------------------------------------- 热键
    def _setup_hotkeys(self):
        # RegisterHotKey 需要一个真实窗口句柄接收 WM_HOTKEY。
        # 用一个专用隐藏窗口，不借用结果窗 —— 结果窗的句柄被 Qt
        # 重新创建时热键会静默失效。
        self._hk_window = QWidget(None)
        self._hk_window.setWindowTitle("_hotkey_sink")
        self._hk_window.resize(1, 1)
        self._hk_window.setAttribute(Qt.WA_DontShowOnScreen, True)
        self._hk_window.show()   # 必须 show 一次才有有效的 HWND
        hwnd = int(self._hk_window.winId())

        self.hotkeys = HotkeyManager(hwnd, self)
        self.hotkeys.install(self.qapp)
        self.hotkeys.triggered.connect(self._on_hotkey)

        bound = []
        for hid, specs, name in (
            (HK_SNIP, HOTKEY_SNIP, "截图标注"),
            (HK_CAPTURE, HOTKEY_CAPTURE, "框选识别"),
            (HK_FULL, HOTKEY_FULL, "整图转文本"),
            (HK_HOVER, HOTKEY_HOVER, "取词模式"),
            (HK_PIN, HOTKEY_PIN, "贴图"),
        ):
            for spec in specs:
                if self.hotkeys.register(hid, spec):
                    bound.append(f"{spec.upper()} {name}")
                    self._hotkey_labels[hid] = spec.upper()
                    break
            else:
                print(f"[warn] 热键 {specs[0]} 全部被占用，{name} 仅托盘可用")
        print("[hotkey] 已注册: " + (" | ".join(bound) if bound else "无"))

    def _on_hotkey(self, hid: int):
        if hid == HK_SNIP:
            self.start_capture(MODE_SNIP)
        elif hid == HK_CAPTURE:
            self.start_capture(MODE_TRANSLATE)
        elif hid == HK_FULL:
            self.start_full_image()
        elif hid == HK_HOVER:
            self.start_hover()
        elif hid == HK_PIN:
            self.pin_current_or_clipboard()

    def pin_current_or_clipboard(self):
        """F3：截图模式内贴当前选区；否则贴剪贴板图片。"""
        ov = self.overlay
        if ov is not None:
            if ov.mode == MODE_SNIP and ov._sel is not None and not ov._closed:
                ov.session.pin()
            return
        if not self.pin_from_clipboard():
            self.tray.showMessage(
                "截图识字", "剪贴板里没有图片", QSystemTrayIcon.Information, 1800
            )

    def pin_from_clipboard(self) -> bool:
        pin = self.pin_manager.create_from_clipboard()
        return pin is not None

    # ---------------------------------------------------- 流程
    def _preload(self):
        t = time.perf_counter()
        ocr_engine.preload()   # 内部已包含模型加载 + 一次推理 + 翻译预热
        print(f"[ocr] 预热完成 {time.perf_counter() - t:.2f}s")

    def start_capture(self, mode: str = MODE_TRANSLATE):
        if not isinstance(mode, str):   # QAction/QPushButton 的 checked 参数
            mode = MODE_TRANSLATE
        if self._busy:
            return
        self._busy = True
        self._capture_mode = mode
        self._ocr_generation += 1
        QTimer.singleShot(120, self._open_overlay)  # 等修饰键松开

    def _open_overlay(self):
        self.window.hide()
        prev = self.overlay
        if prev is not None:
            # 旧遮罩持有整张桌面截图（多屏 4K 可达数百 MB），必须主动释放
            prev.close_all()
            prev.deleteLater()
        try:
            self.overlay = CaptureOverlay(mode=self._capture_mode)
        except Exception as exc:
            self._busy = False
            self.overlay = None
            QMessageBox.warning(None, "截图失败", str(exc))
            return
        self.overlay.save_dir = self.save_dir
        self.overlay.set_programmer_mode(self.programmer_mode)
        self.overlay.mode_changed = self._on_overlay_mode_changed
        self.overlay.pin_requested.connect(self._on_pin_requested)
        if self.overlay.mode == MODE_TRANSLATE:
            self.overlay.selection_changed.connect(self._on_selection)
            self.overlay.retranslate_requested.connect(self._on_retranslate)
        self.overlay.closed.connect(self._on_cancel)
        self.overlay.show()
        self.overlay.raise_()
        self.overlay.activateWindow()
        self.overlay.setFocus()

    def _on_pin_requested(self, pixmap: QPixmap, logical_size: QSize, pos: QPoint):
        try:
            self.pin_manager.create(pixmap, logical_size, pos)
        except Exception as exc:
            self.tray.showMessage(
                "截图识字", f"贴图失败: {exc}", QSystemTrayIcon.Warning, 2500
            )

    def start_full_image(self):
        """整图转文本：抓当前屏幕整张，直接 OCR。"""
        if self._busy:
            return
        self._busy = True
        self._ocr_generation += 1
        self.window.hide()
        QTimer.singleShot(100, self._do_full_image)

    def _do_full_image(self):
        try:
            shot, _geo, _scale = grab_all()
        except Exception as exc:
            self._busy = False
            self.tray.showMessage("截图识字", f"截屏失败: {exc}", QSystemTrayIcon.Warning, 2500)
            return
        if shot.isNull():
            self._busy = False
            self.tray.showMessage("截图识字", "截屏失败", QSystemTrayIcon.Warning, 2000)
            return
        self._run_ocr(shot)

    def start_hover(self):
        """取词模式：抓光标周围一块，立即识别。"""
        if self._busy:
            return
        self._busy = True
        self.window.hide()
        self._ocr_generation += 1
        QTimer.singleShot(100, self._do_hover)

    def _do_hover(self):
        try:
            cursor_pos = QCursor.pos()
            crop, _rect = grab_around(cursor_pos, HOVER_SIZE)
        except Exception as exc:
            self._busy = False
            self.tray.showMessage("截图识字", f"取词截屏失败: {exc}", QSystemTrayIcon.Warning, 2500)
            return
        if crop.isNull() or crop.width() == 0:
            self._busy = False
            self.tray.showMessage("截图识字", "取词截屏失败", QSystemTrayIcon.Warning, 2000)
            return
        self._run_ocr(crop)

    def _on_overlay_mode_changed(self, enabled: bool):
        """选区层切换代码模式时同步全局状态和结果窗。"""
        self.programmer_mode = enabled
        self.window.programmer_mode = enabled
        self.window.btn_programmer.setChecked(enabled)
        self._ocr_generation += 1

    def _on_selection(self, pixmap, selection_rect):
        """选区稳定（框选完成 / 移动 / 缩放结束）后触发识别。"""
        overlay = self.overlay
        if overlay is None:
            return
        self._ocr_generation += 1
        generation = self._ocr_generation

        try:
            pil = qpixmap_to_pil(pixmap)
        except Exception as exc:
            overlay.show_message(f"截图失败: {exc}")
            return

        def work():
            t = time.perf_counter()
            try:
                text = ocr_engine.recognize(pil)
                err = None
            except Exception as exc:
                text, err = "", exc
            finally:
                dt = time.perf_counter() - t
                try:
                    print(f"[ocr] {dt * 1000:.0f}ms  {len(text)} 字")
                except Exception:
                    pass

            def apply():
                if generation != self._ocr_generation or overlay is None \
                        or overlay is not self.overlay:
                    return
                if err is not None:
                    overlay.show_message(f"识别失败: {err}")
                    return
                if not text.strip():
                    overlay.show_message("没有识别到文字")
                    return
                overlay.show_source(text)
                self._start_translate(text, overlay, generation)

            # 必须保证信号发出，否则 _busy 会永久卡住
            try:
                self._ocr_bridge.finished.emit(text, err, apply, generation)
            except Exception as exc:
                try:
                    self._ocr_bridge.finished.emit(
                        "", exc, apply, generation
                    )
                except Exception:
                    pass

        threading.Thread(target=work, daemon=True).start()

    def _start_translate(self, text, overlay, generation):
        mode = "programmer" if self.programmer_mode else "general"

        def work():
            try:
                result = ocr_engine.translate(
                    text, source="auto", target="zh-Hans", mode=mode,
                )
                err = None
            except Exception as exc:
                result, err = "", exc

            # 程序员模式额外给出标识符拆词解释（失败不影响主译文）
            # ocr_engine.translate 在程序员模式下已把标识符解释并入译文，
            # 这里不再重复计算/拼接。
            notes: list[str] = []

            def apply():
                if generation != self._ocr_generation or overlay is None \
                        or overlay is not self.overlay:
                    return
                if err is not None:
                    overlay.panel.set_status("翻译失败（已保留原文）")
                    return
                overlay.show_translation(result, notes)

            try:
                self._ocr_bridge.finished.emit(result, err, apply, generation)
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()

    def _on_cancel(self):
        self._ocr_generation += 1
        self._busy = False
        old = self.overlay
        self.overlay = None
        if old is not None:
            old.deleteLater()

    def _on_retranslate(self, text: str):
        """选区层切换代码模式：只重翻译，不再跑 OCR。"""
        overlay = self.overlay
        if overlay is None or not text.strip():
            return
        self._ocr_generation += 1
        generation = self._ocr_generation
        self._start_translate(text, overlay, generation)

    def _run_ocr(self, pixmap: QPixmap):
        """整图 / 取词模式：仍用完整结果窗，不走选区层。"""
        self._busy = True
        generation = self._ocr_generation
        try:
            pil = qpixmap_to_pil(pixmap)
        except Exception as exc:
            self._busy = False
            QMessageBox.warning(None, "截图转换失败", str(exc))
            return

        def work():
            t = time.perf_counter()
            try:
                text = ocr_engine.recognize(pil)
                err = None
            except Exception as exc:
                text, err = "", exc
            finally:
                dt = time.perf_counter() - t
                try:
                    print(f"[ocr] {dt * 1000:.0f}ms  {len(text)} 字")
                except Exception:
                    pass
            try:
                self._ocr_bridge.finished.emit(text, err, None, generation)
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()

    def _on_ocr_done(self, text, err, payload, generation):
        # payload 是回调（选区层）或 None（整图/取词）
        if callable(payload):
            payload()
            return

        if generation != self._ocr_generation:
            return
        self._busy = False
        self.overlay = None
        if err is not None:
            QMessageBox.warning(None, "识别失败", str(err))
            return
        if not text or not text.strip():
            self.tray.showMessage(
                "截图识字", "没有识别到文字", QSystemTrayIcon.Information, 1500
            )
            return

        self.window.show_result(
            text, anchor=None, translate=True, selection_rect=None,
            programmer_mode=self.programmer_mode,
        )

    # ---------------------------------------------------- 退出
    def quit(self):
        settings_dialog = getattr(self, "_settings_dialog", None)
        if settings_dialog is not None:
            settings_dialog.close()
        try:
            if self.hotkeys:
                self.hotkeys.unregister_all()   # 内部会摘除 native filter
        except Exception:
            pass
        try:
            self.pin_manager.close_all()
        except Exception:
            pass
        try:
            if self.overlay is not None:
                self.overlay.close_all()
                self.overlay.deleteLater()
                self.overlay = None
        except Exception:
            pass
        try:
            self._hk_window.hide()
            self._hk_window.deleteLater()
        except Exception:
            pass
        self.window.hide()
        self.tray.hide()
        QApplication.quit()


def install_excepthook():
    def hook(tp, val, tb):
        import traceback

        traceback.print_exception(tp, val, tb)
        try:
            QMessageBox.critical(None, "未捕获异常", f"{tp.__name__}: {val}")
        except Exception:
            pass

    sys.excepthook = hook


def main():
    install_excepthook()
    qapp = QApplication(sys.argv)
    qapp.setQuitOnLastWindowClosed(False)
    qapp.setApplicationName("截图识字")

    from PySide6.QtNetwork import QLocalServer, QLocalSocket

    server_name = "jietu-desktop-" + os.environ.get("USERNAME", "default")
    existing = QLocalSocket()
    existing.connectToServer(server_name)
    if existing.waitForConnected(500):
        existing.write(b"restart")
        existing.waitForBytesWritten(1000)
        if not existing.waitForDisconnected(5000):
            QMessageBox.warning(None, "截图识字", "旧程序尚未退出，请先从托盘退出后重新启动。")
            return
    server = QLocalServer(qapp)
    if not server.listen(server_name):
        QMessageBox.warning(None, "截图识字", server.errorString())
        return
    app = App(qapp)

    def replace_instance():
        socket = server.nextPendingConnection()
        if socket is not None:
            socket.close()
            socket.deleteLater()
        app.quit()

    server.newConnection.connect(replace_instance)
    sys.exit(qapp.exec())


if __name__ == "__main__":
    main()
