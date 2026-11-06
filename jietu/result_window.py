"""识别结果浮窗 —— 参照网易有道识图的横条工具栏样式。

结构：
    ┌─────────────────────────────────────────────┐
    │ 原文 / 译文 切换                    ✕      │  标题条
    ├─────────────────────────────────────────────┤
    │                                             │
    │           识别 / 翻译文本区                 │
    │                                             │
    ├─────────────────────────────────────────────┤
    │ 英语 ⇄ 简体中文 | 复制 提取文本 翻译         │  底部工具栏
    └─────────────────────────────────────────────┘
"""

import threading

from PySide6.QtCore import QObject, QPoint, Qt, Signal
from PySide6.QtGui import QFont, QGuiApplication, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

ACCENT = "#e8503a"  # 有道同款橙红


class TranslationBridge(QObject):
    # result, error, generation, source, identifier notes
    finished = Signal(str, object, int, str, object)


class SegButton(QPushButton):
    """原文/译文 分段按钮。"""

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(26)


class ResultWindow(QWidget):
    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating, False)
        self.setWindowTitle("截图识字")
        self.resize(560, 380)

        self._source = ""
        self._translated = ""
        self._view = "source"
        self.programmer_mode = False
        self.mode_changed = None
        self._translation_generation = 0
        self._translation_pending = False
        self._translation_bridge = TranslationBridge()
        self._translation_bridge.finished.connect(self._on_translation_done)
        self._selection_rect = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())
        root.addWidget(self._build_body(), 1)
        root.addWidget(self._build_toolbar())

        self._apply_style()
        self._drag = None

    # ------------------------------------------------ 标题条
    def _build_header(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("header")
        bar.setFixedHeight(34)

        hb = QHBoxLayout(bar)
        hb.setContentsMargins(8, 0, 6, 0)
        hb.setSpacing(2)

        self.btn_src = SegButton("原文")
        self.btn_dst = SegButton("译文")
        self.btn_src.setChecked(True)
        self.btn_src.clicked.connect(lambda: self._switch("source"))
        self.btn_dst.clicked.connect(lambda: self._switch("target"))

        hb.addWidget(self.btn_src)
        hb.addWidget(self.btn_dst)
        hb.addStretch(1)

        self.btn_programmer = QPushButton("代码")
        self.btn_programmer.setObjectName("modeBtn")
        self.btn_programmer.setCheckable(True)
        self.btn_programmer.setCursor(Qt.PointingHandCursor)
        self.btn_programmer.setToolTip("程序员翻译：保留标识符、API、路径、URL 和代码结构")
        self.btn_programmer.clicked.connect(self._toggle_programmer_mode)
        hb.addWidget(self.btn_programmer)

        self.status = QLabel("")
        self.status.setObjectName("status")
        hb.addWidget(self.status)

        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("closeBtn")
        self.btn_close.setCursor(Qt.PointingHandCursor)
        self.btn_close.setFixedSize(26, 24)
        self.btn_close.clicked.connect(self.hide)
        hb.addWidget(self.btn_close)
        return bar

    # ------------------------------------------------ 文本区
    def _build_body(self) -> QWidget:
        body = QWidget()
        body.setObjectName("body")
        vb = QVBoxLayout(body)
        vb.setContentsMargins(0, 0, 0, 0)
        vb.setSpacing(0)

        self.editor = QTextEdit()
        self.editor.setObjectName("editor")
        self.editor.setAcceptRichText(False)
        self.editor.setFont(QFont("Microsoft YaHei UI", 10))
        self.editor.setLineWrapMode(QTextEdit.WidgetWidth)
        vb.addWidget(self.editor)

        # 左右切换的窄条
        nav = QWidget()
        nav.setObjectName("navBar")
        nav.setFixedHeight(22)
        nb = QHBoxLayout(nav)
        nb.setContentsMargins(12, 0, 12, 0)
        self.nav_hint = QLabel("")
        self.nav_hint.setObjectName("navHint")
        nb.addStretch(1)
        nb.addWidget(self.nav_hint)
        vb.addWidget(nav)
        return body

    # ------------------------------------------------ 底部工具栏
    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("toolbar")
        bar.setFixedHeight(46)

        hb = QHBoxLayout(bar)
        hb.setContentsMargins(10, 6, 10, 6)
        hb.setSpacing(6)

        self.lang_src = QComboBox()
        self.lang_src.addItems(["英语", "中文", "日文", "韩文", "自动"])
        self.lang_src.setCurrentText("自动")
        self.lang_src.setFixedSize(76, 28)

        swap = QPushButton("⇄")
        swap.setObjectName("iconBtn")
        swap.setCursor(Qt.PointingHandCursor)
        swap.setFixedSize(26, 28)
        swap.setToolTip("交换语言")
        swap.clicked.connect(self._swap_lang)

        self.lang_dst = QComboBox()
        self.lang_dst.addItems(["简体中文", "英语", "日文", "韩文"])
        self.lang_dst.setCurrentText("简体中文")
        self.lang_dst.setFixedSize(92, 28)

        hb.addWidget(self.lang_src)
        hb.addWidget(swap)
        hb.addWidget(self.lang_dst)
        hb.addWidget(self._vline())
        hb.addStretch(1)

        self.btn_copy = self._tool_btn("复制")
        self.btn_extract = self._tool_btn("提取文本")
        self.btn_translate = self._tool_btn("翻译", primary=True)
        self.btn_more = self._tool_btn("⋯")

        self.btn_copy.clicked.connect(self.copy_text)
        self.btn_extract.clicked.connect(self.extract_text)
        self.btn_translate.clicked.connect(self.translate_now)
        self.btn_more.clicked.connect(self._show_more)

        for b in (self.btn_copy, self.btn_extract, self.btn_translate,
                  self.btn_more):
            hb.addWidget(b)
        return bar

    @staticmethod
    def _tool_btn(text: str, primary: bool = False) -> QPushButton:
        b = QPushButton(text)
        b.setObjectName("primaryBtn" if primary else "toolBtn")
        b.setCursor(Qt.PointingHandCursor)
        b.setFixedHeight(30)
        return b

    @staticmethod
    def _vline() -> QFrame:
        f = QFrame()
        f.setObjectName("vline")
        f.setFixedSize(1, 22)
        f.setStyleSheet("background: #454a53; border: none;")
        return f

    # ------------------------------------------------ 样式
    def _apply_style(self):
        self.setStyleSheet(
            f"""
            ResultWindow {{ background: #24262b; border: 1px solid #3a3d44; }}
            #header {{ background: #2c2f35; border-bottom: 1px solid #3a3d44; }}
            #body {{ background: #24262b; }}
            #status {{ color: #7d838d; font-size: 11px; padding-right: 4px; }}
            #navBar {{ background: #202227; border-top: 1px solid #2f3238; }}
            #navHint {{ color: #656b75; font-size: 11px; }}
            #editor {{ background: #24262b; color: #e8eaed; border: none;
                       selection-background-color: {ACCENT}; padding: 10px 14px; }}
            #toolbar {{ background: #2c2f35; border-top: 1px solid #3a3d44; }}
            #vline {{ background: #3f434b; border: none; margin: 4px 4px; }}

            QPushButton#modeBtn {{ background: #3a3e46; color: #aeb4bd; border: none;
                                    border-radius: 4px; padding: 0 9px; font-size: 11px; }}
            QPushButton#modeBtn:checked {{ background: {ACCENT}; color: white; }}
            QPushButton#closeBtn {{ background: transparent; color: #8b919a;
                                    font-size: 15px; border: none; border-radius: 4px; }}
            QPushButton#closeBtn:hover {{ background: #d33a2c; color: white; }}

            QPushButton#toolBtn {{ background: #3a3e46; color: #d5d9df; border: none;
                                   border-radius: 4px; padding: 0 12px; font-size: 12px; }}
            QPushButton#toolBtn:hover {{ background: #474c55; }}
            QPushButton#toolBtn:pressed {{ background: #30343a; }}

            QPushButton#primaryBtn {{ background: {ACCENT}; color: white; border: none;
                                      border-radius: 4px; padding: 0 14px;
                                      font-size: 12px; font-weight: 500; }}
            QPushButton#primaryBtn:hover {{ background: #f25f47; }}
            QPushButton#primaryBtn:pressed {{ background: #d0422d; }}

            QPushButton#iconBtn {{ background: #3a3e46; color: #b9bfc7; border: none;
                                   border-radius: 4px; font-size: 13px; }}
            QPushButton#iconBtn:hover {{ background: #474c55; color: white; }}

            /* 原文/译文 分段按钮 */
            QPushButton[size] {{ }}
            QComboBox {{ background: #3a3e46; color: #d5d9df; border: none;
                         border-radius: 4px; padding: 0 8px; font-size: 12px; }}
            QComboBox:hover {{ background: #474c55; }}
            QComboBox::drop-down {{ border: none; width: 16px; }}
            QComboBox QAbstractItemView {{ background: #3a3e46; color: #d5d9df;
                                           selection-background-color: {ACCENT};
                                           border: 1px solid #4a4f58; outline: none; }}
            QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
            QScrollBar::handle:vertical {{ background: #4a4f58; border-radius: 5px;
                                           min-height: 30px; }}
            QScrollBar::handle:vertical:hover {{ background: #5b616b; }}
            QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
            """
        )
        # 分段按钮单独设样式（QSS 里用 objectName 区分）
        for b, on in ((self.btn_src, True), (self.btn_dst, False)):
            b.setStyleSheet(
                f"""
                QPushButton {{ background: transparent; color: #9aa0a9;
                               border: none; border-radius: 4px;
                               padding: 0 12px; font-size: 12px; }}
                QPushButton:hover {{ color: #d5d9df; }}
                QPushButton:checked {{ background: #3a3e46; color: white; }}
                """
            )

    # ------------------------------------------------ 对外接口
    def show_result(self, source: str, anchor: QPoint | None = None,
                    translate: bool = True, image=None, selection_rect=None,
                    programmer_mode=None):
        self._selection_rect = selection_rect
        if programmer_mode is not None:
            self.programmer_mode = bool(programmer_mode)
        # 新一次识别结果：作废旧请求、复位所有翻译状态，
        # 否则上一次未完成的翻译会让这次直接 return，永远不出译文。
        self._translation_generation += 1
        self._translation_pending = False
        self._source = source
        self._translated = ""
        self._view = "source"
        self.btn_programmer.setChecked(self.programmer_mode)
        self.btn_src.setChecked(True)
        self.btn_dst.setChecked(False)
        self.editor.setPlainText(source)
        self.status.setText(f"{len(source)} 字")
        self.nav_hint.setText("Alt+1 原文 · Alt+2 译文 · Ctrl+C 复制")

        if self._selection_rect is not None:
            # 选区结果现在由 CaptureOverlay 内嵌面板负责，这里不再另开浮层
            return

        self._place(anchor)
        self.show()
        self.raise_()
        self.activateWindow()
        self.editor.setFocus()
        self.editor.moveCursor(QTextCursor.Start)

        if translate and source.strip():
            self.translate_now()

    def _place(self, anchor: QPoint | None):
        screen = QGuiApplication.screenAt(anchor) if anchor else None
        screen = screen or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        w, h = self.width(), self.height()

        if anchor is None:
            x = area.center().x() - w // 2
            y = area.center().y() - h // 2
        else:
            x = anchor.x() + 16
            y = anchor.y() + 16
            if x + w > area.right():
                x = anchor.x() - w - 16
            if y + h > area.bottom():
                y = anchor.y() - h - 16
            x = max(area.left() + 6, min(x, area.right() - w - 6))
            y = max(area.top() + 6, min(y, area.bottom() - h - 6))
        self.move(int(x), int(y))

    def _toggle_programmer_mode(self, enabled: bool):
        self.programmer_mode = bool(enabled)
        if self.mode_changed:
            self.mode_changed(self.programmer_mode)
        # clicked(bool) 传入的状态可能与真实 checked 不一致（例如程序化调用），
        # 这里以传入值为准并回写按钮，保证 UI 状态一致
        if self.btn_programmer.isChecked() != self.programmer_mode:
            self.btn_programmer.setChecked(self.programmer_mode)
        self._translation_generation += 1
        self._translated = ""
        self.status.setText("程序员模式" if self.programmer_mode else "普通模式")
        if not self._source.strip():
            return

        # 旧请求已在飞：它的结果会因 generation 过期被丢弃。
        # 这里必须立刻接管状态并发起新请求，否则旧结果回来时
        # 走的是过期分支（不碰 pending），按钮会永久禁用。
        self._translation_pending = False
        self.btn_translate.setEnabled(True)
        self.translate_now()

    # ------------------------------------------------ 视图切换
    def _switch(self, view: str):
        self._view = view
        self.btn_src.setChecked(view == "source")
        self.btn_dst.setChecked(view == "target")
        if view == "source":
            self.editor.setPlainText(self._source)
        else:
            if not self._translated and self._source.strip():
                # 还没翻译过：切过去的同时发起翻译
                self.editor.setPlainText("")
                self._view = "target"
                self.translate_now()
                return
            self.editor.setPlainText(self._translated or "")
        self.editor.moveCursor(QTextCursor.Start)

    # ------------------------------------------------ 动作
    def current_text(self) -> str:
        return self.editor.toPlainText()

    def translate_now(self):
        text = self._source.strip()
        if not text:
            return
        # 已有请求在跑时不排队等待（旧结果会被 generation 作废），
        # 直接发起新请求并接管状态，避免 pending 永久卡死。
        from .ocr_engine import language_code, translate as do_translate

        self._translation_generation += 1
        generation = self._translation_generation
        self._translation_pending = True
        self.status.setText("翻译中…")
        self.btn_translate.setEnabled(False)

        # 在 GUI 线程取控件值，worker 里不能碰 Qt 控件
        src_code = language_code(self.lang_src.currentText())
        dst_code = language_code(self.lang_dst.currentText())
        mode = "programmer" if self.programmer_mode else "general"

        def work():
            try:
                result, error = do_translate(
                    text, source=src_code, target=dst_code, mode=mode,
                ), None
            except Exception as exc:
                result, error = "", exc

            # ocr_engine.translate 已把标识符解释并入译文，这里不再拼接
            try:
                self._translation_bridge.finished.emit(
                    result, error, generation, text, []
                )
            except RuntimeError:
                # 窗口已在退出流程中销毁，丢弃结果即可
                pass

        threading.Thread(target=work, daemon=True).start()

    def _on_translation_done(self, result, error, generation, source, notes=None):
        # 过期请求：可能是更早的请求晚到，绝不能动当前请求的状态
        if generation != self._translation_generation:
            return
        if source != self._source.strip():
            return

        self._translation_pending = False
        self.btn_translate.setEnabled(True)
        if error is not None:
            self.status.setText("翻译失败")
            return
        self._translated = result
        self.status.setText(f"{len(source)} 字 · 已翻译")
        if self._view == "target":
            self.editor.setPlainText(self._translated)
            self.editor.moveCursor(QTextCursor.Start)



    def extract_text(self):
        """纯提取文本：只保留原文字，不做翻译。"""
        self._switch("source")
        self.copy_text()
        self.status.setText("已提取并复制")

    def copy_text(self):
        QApplication.clipboard().setText(self.editor.toPlainText())
        self.status.setText("已复制")


    def _show_more(self):
        from PySide6.QtWidgets import QMenu

        menu = QMenu(self)
        menu.setStyleSheet(
            f"""
            QMenu {{ background: #2c2f35; color: #d5d9df; border: 1px solid #4a4f58;
                     padding: 4px; }}
            QMenu::item {{ padding: 6px 24px; border-radius: 3px; }}
            QMenu::item:selected {{ background: {ACCENT}; color: white; }}
            """
        )
        menu.addAction("重新框选  Alt+D", self._request_recapture)
        menu.addAction("整图转文本  Alt+Q", self._request_full)
        menu.addSeparator()
        menu.addAction("保存为 txt…", self._save_txt)
        menu.exec(self.btn_more.mapToGlobal(QPoint(0, -menu.sizeHint().height())))

    def _request_recapture(self):
        cb = getattr(self, "_on_recapture", None)
        self.hide()
        if cb:
            cb()

    def _request_full(self):
        cb = getattr(self, "_on_fullimage", None)
        self.hide()
        if cb:
            cb()

    def _save_txt(self):
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getSaveFileName(
            self, "保存文本", "识别结果.txt", "文本文件 (*.txt)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.editor.toPlainText())
            self.status.setText("已保存")
        except OSError as exc:
            self.status.setText(f"保存失败: {exc}")

    def _swap_lang(self):
        src, dst = self.lang_src.currentText(), self.lang_dst.currentText()
        self.lang_src.setCurrentText(dst.replace("简体", ""))
        self.lang_dst.setCurrentText(src)

    # ------------------------------------------------ 交互
    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.hide()
        elif e.matches("Ctrl+C"):
            self.copy_text()
        elif e.matches("Ctrl+T"):
            self.translate_now()
        else:
            super().keyPressEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and e.position().y() < 34:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            e.accept()

    def mouseMoveEvent(self, e):
        if self._drag and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag)
            e.accept()

    def mouseReleaseEvent(self, e):
        self._drag = None

    def closeEvent(self, e):
        e.ignore()
        self.hide()
