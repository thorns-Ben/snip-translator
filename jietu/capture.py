"""全屏框选 + 选区翻译层（单窗口，无二次弹窗）。

设计要点：
  * 框选后窗口不关闭，直接把翻译结果画在同一个全屏窗口里，
    从根本上消除"闪一下再弹一个框"。
  * 原图 `_shot` 全程保留，所以移动/缩放选区后可以立即重新裁剪重新识别。
  * 关闭 = 关掉整层：✕ 按钮 / Esc / 点击选区与结果面板以外的地方。

交互：
  拖动空白处      新建选区
  拖动选区内部    移动（松手后自动重新识别）
  拖动八个手柄    缩放（松手后自动重新识别）
  双击 / Enter    立即重新识别
  Esc / 右键      关闭
"""

from dataclasses import dataclass

from PySide6.QtCore import QPoint, QPointF, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QTransform
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

MIN_SIZE = 8
HANDLE = 8
HIT_PAD = 5
REDETECT_DELAY = 280     # 移动/缩放后重新识别的防抖（毫秒）
PANEL_WIDTH = 460
PANEL_GAP = 8

IDLE, SELECTING, READY = "idle", "selecting", "ready"

MODE_TRANSLATE = "translate"
MODE_SNIP = "snip"

ACCENT = "#e8503a"


def virtual_geometry() -> QRect:
    geo = QRect()
    for screen in QGuiApplication.screens():
        geo = geo.united(screen.geometry())
    return geo


@dataclass
class NativeExport:
    """Crop and exact overlay-logical → output/source pixel mappings."""

    crop: QPixmap
    transform: QTransform
    source: QPixmap
    origin: QPointF
    scale_x: float
    scale_y: float
    source_rect: QRect


def grab_all(native_screens: list | None = None) -> tuple[QPixmap, QRect, float]:
    """抓整个虚拟桌面，返回 (物理像素 pixmap, 逻辑矩形, 缩放系数)。"""
    geo = virtual_geometry()
    if geo.isEmpty():
        return QPixmap(), geo, 1.0

    dpr = max((s.devicePixelRatio() for s in QGuiApplication.screens()), default=1.0)
    phys_w = max(1, int(round(geo.width() * dpr)))
    phys_h = max(1, int(round(geo.height() * dpr)))

    shot = QPixmap(phys_w, phys_h)
    shot.fill(QColor(0, 0, 0))

    p = QPainter(shot)
    try:
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        for screen in QGuiApplication.screens():
            sg = screen.geometry()
            pix = screen.grabWindow(0)
            pix.setDevicePixelRatio(1.0)
            if native_screens is not None:
                native_screens.append((QRect(sg), QPixmap(pix)))
            tw = max(1, int(round(sg.width() * dpr)))
            th = max(1, int(round(sg.height() * dpr)))
            if pix.width() != tw or pix.height() != th:
                pix = pix.scaled(tw, th, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            p.drawPixmap(
                int(round((sg.x() - geo.x()) * dpr)),
                int(round((sg.y() - geo.y()) * dpr)),
                pix,
            )
    finally:
        p.end()

    scale = phys_w / geo.width() if geo.width() else dpr
    return shot, geo, scale


def grab_around(point: QPoint, logical_size: int) -> tuple[QPixmap, QRect]:
    """取词模式：返回截图和它在虚拟桌面中的全局逻辑矩形。"""
    screen = QGuiApplication.screenAt(point) or QGuiApplication.primaryScreen()
    sg = screen.geometry()

    half = logical_size // 2
    x0 = max(sg.left(), min(point.x() - half, sg.right() - logical_size))
    y0 = max(sg.top(), min(point.y() - half, sg.bottom() - logical_size))

    rel_x = x0 - sg.x()
    rel_y = y0 - sg.y()
    w = min(logical_size, sg.width() - rel_x)
    h = min(logical_size, sg.height() - rel_y)

    pix = screen.grabWindow(0, rel_x, rel_y, w, h)
    pix.setDevicePixelRatio(1.0)
    return pix, QRect(x0, y0, w, h)


class _ResultPanel(QWidget):
    """贴在选区旁的结果面板：状态行 + 译文 + 操作按钮。"""

    def __init__(self, overlay: "CaptureOverlay"):
        super().__init__(overlay)
        self.overlay = overlay
        self.setObjectName("resultPanel")
        self.setFixedWidth(PANEL_WIDTH)
        # 子控件不是独立窗口，必须显式不透明，否则会透出底下压暗的桌面
        self.setAutoFillBackground(True)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        # QSS 的 background-color 对 QWidget 子类需要这个属性才会真正绘制
        self.setAttribute(Qt.WA_StyledBackground, True)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 9, 10, 9)
        root.setSpacing(7)

        # ---- 状态行
        head = QHBoxLayout()
        head.setSpacing(6)
        self.status = QLabel("识别中…")
        self.status.setObjectName("pStatus")
        head.addWidget(self.status)
        head.addStretch(1)
        self.btn_programmer = QPushButton("代码")
        self.btn_programmer.setObjectName("pMode")
        self.btn_programmer.setCheckable(True)
        self.btn_programmer.setCursor(Qt.PointingHandCursor)
        self.btn_programmer.setFixedHeight(20)
        self.btn_programmer.setToolTip("程序员翻译：保留标识符、API、路径、URL 和代码结构")
        self.btn_programmer.clicked.connect(overlay.toggle_programmer_mode)
        head.addWidget(self.btn_programmer)
        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("pClose")
        self.btn_close.setCursor(Qt.PointingHandCursor)
        self.btn_close.setFixedSize(22, 20)
        self.btn_close.setToolTip("关闭 (Esc)")
        self.btn_close.clicked.connect(overlay.close_all)
        head.addWidget(self.btn_close)
        root.addLayout(head)

        # ---- 正文
        self.text = QTextEdit()
        self.text.setObjectName("pText")
        self.text.setReadOnly(True)
        self.text.setAcceptRichText(False)
        self.text.setFrameShape(QTextEdit.NoFrame)
        self.text.setLineWrapMode(QTextEdit.WidgetWidth)
        self.text.setFixedHeight(34)
        root.addWidget(self.text)

        # ---- 按钮
        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.btn_copy = self._btn("复制")
        self.btn_extract = self._btn("提取文本")
        self.btn_redetect = self._btn("重新识别")
        for b in (self.btn_copy, self.btn_extract, self.btn_redetect):
            bar.addWidget(b)
        bar.addStretch(1)
        root.addLayout(bar)

        self.btn_copy.clicked.connect(overlay.copy_result)
        self.btn_extract.clicked.connect(overlay.copy_source)
        self.btn_redetect.clicked.connect(overlay.redetect)

        self.setStyleSheet(f"""
            #resultPanel {{ background-color: #26292e; border: 1px solid #4b5059;
                            border-radius: 8px; }}
            #pStatus {{ color: #9aa0a9; font-size: 11px; background: transparent; }}
            #pText {{ background: transparent; color: #e9ebef; border: none;
                      font-size: 13px; padding: 0; }}
            QPushButton {{ background: #3a3e46; color: #d5d9df; border: none;
                           border-radius: 4px; padding: 0 12px; min-height: 27px;
                           font-size: 12px; }}
            QPushButton:hover {{ background: #4a5059; }}
            QPushButton#pClose {{ background: transparent; color: #9aa0a9;
                                  min-width: 20px; padding: 0; font-size: 13px; }}
            QPushButton#pClose:hover {{ background: #d33a2c; color: white; }}
            QPushButton#pMode {{ background: #3a3e46; color: #aeb4bd; min-height: 20px;
                                 padding: 0 8px; font-size: 11px; }}
            QPushButton#pMode:checked {{ background: {ACCENT}; color: white; }}
            QScrollBar:vertical {{ background: transparent; width: 8px; }}
            QScrollBar::handle:vertical {{ background: #4a4f58; border-radius: 4px;
                                           min-height: 20px; }}
            QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
        """)

    @staticmethod
    def _btn(text: str) -> QPushButton:
        b = QPushButton(text)
        b.setCursor(Qt.PointingHandCursor)
        return b

    # ---------------------------------------------------- 内容
    def set_status(self, text: str):
        self.status.setText(text)
        self.adjustSize()

    def set_text(self, text: str):
        self.text.setPlainText(text)
        self._fit_height()

    def _fit_height(self):
        doc = self.text.document()
        doc.setTextWidth(self.text.viewport().width() or (PANEL_WIDTH - 40))
        h = int(doc.size().height()) + 8
        self.text.setFixedHeight(max(30, min(h, 150)))
        self.adjustSize()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.overlay.close_all()
        else:
            super().keyPressEvent(e)


class CaptureOverlay(QWidget):
    """铺满虚拟桌面的框选层，同时也是翻译结果显示层。"""

    # 选区稳定后（框选完成 / 移动结束 / 缩放结束）发出，供上层做 OCR
    selection_changed = Signal(object, QRect)
    retranslate_requested = Signal(str)   # 只重翻译，不重跑 OCR
    pin_requested = Signal(object, object, object)  # 贴图: pixmap, QSize, 全局 QPoint
    closed = Signal()

    def __init__(self, mode: str = MODE_TRANSLATE):
        super().__init__(None)
        self.mode = mode
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.capture_cursor = self._make_capture_cursor()
        self.setCursor(self.capture_cursor)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self._native_screens = []
        if mode == MODE_SNIP:
            self._shot, self._geo, self._scale = grab_all(self._native_screens)
        else:
            self._shot, self._geo, self._scale = grab_all()
        self._original_shot_key = self._shot.cacheKey()
        self.setGeometry(self._geo)
        self.save_dir = None

        self._origin: QPoint | None = None
        self._current: QPoint | None = None
        self._sel: QRect | None = None
        self._closed = False
        self._state = IDLE
        self._drag_mode: str | None = None
        self._drag_handle: str | None = None
        self._drag_start = QPoint()
        self._drag_rect = QRect()

        self._source_text = ""
        self._result_text = ""
        self.programmer_mode = False
        self.mode_changed = None  # 可选回调：签名 (bool)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(REDETECT_DELAY)
        self._debounce.timeout.connect(self._emit_selection)

        self.panel = _ResultPanel(self)
        self.panel.hide()
        self.panel.btn_programmer.setChecked(self.programmer_mode)

        self.session = None
        if mode == MODE_SNIP:
            from .snip import SnipSession

            self.session = SnipSession(self)

    @staticmethod
    def _make_capture_cursor() -> QCursor:
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        # 短臂黑白描边准星，在亮背景和暗背景上都保持可见。
        for color, width in ((QColor("#17191c"), 5), (QColor("#ffffff"), 3)):
            painter.setPen(QPen(color, width, Qt.SolidLine, Qt.SquareCap))
            for x1, y1, x2, y2 in ((15, 5, 15, 11), (15, 19, 15, 25),
                                    (5, 15, 11, 15), (19, 15, 25, 15)):
                painter.drawLine(x1, y1, x2, y2)
        painter.setPen(QPen(QColor("#17191c"), 3))
        painter.drawPoint(15, 15)
        painter.setPen(QPen(QColor("#ffffff"), 1))
        painter.drawPoint(15, 15)
        painter.end()
        return QCursor(pixmap, 15, 15)

    # ---------------------------------------------------- 坐标
    @staticmethod
    def _span_rect(a: QPoint, b: QPoint) -> QRect:
        x1, x2 = sorted((a.x(), b.x()))
        y1, y2 = sorted((a.y(), b.y()))
        return QRect(x1, y1, x2 - x1 + 1, y2 - y1 + 1)

    def _to_phys(self, r: QRect) -> QRect:
        s = self._scale
        return QRect(
            int(r.x() * s), int(r.y() * s), int(r.width() * s), int(r.height() * s)
        )

    def _crop(self, sel: QRect) -> QPixmap:
        phys = self._to_phys(sel).intersected(
            QRect(0, 0, self._shot.width(), self._shot.height())
        )
        return self._shot.copy(phys)

    def _export_layout(self, sel: QRect):
        """Return source, source origin, independent pixel scales and crop bounds."""
        native = (self._native_screens if self._shot.cacheKey()
                  == self._original_shot_key else [])
        global_sel = sel.translated(self._geo.topLeft())
        for geo, pix in native:
            if geo.contains(global_sel) and not pix.isNull():
                origin = QPointF(geo.topLeft() - self._geo.topLeft())
                sx = pix.width() / geo.width()
                sy = pix.height() / geo.height()
                break
        else:
            # Cross-monitor output uses the existing desktop grid, but rebuilds it
            # from retained originals with nearest-neighbour sampling on export.
            pix = self._shot
            origin = QPointF(0, 0)
            sx = sy = self._scale
        x0 = round((sel.x() - origin.x()) * sx)
        y0 = round((sel.y() - origin.y()) * sy)
        x1 = round((sel.x() + sel.width() - origin.x()) * sx)
        y1 = round((sel.y() + sel.height() - origin.y()) * sy)
        bounds = QRect(x0, y0, max(1, x1 - x0), max(1, y1 - y0))
        bounds = bounds.intersected(pix.rect())
        if not native:
            bounds = self._to_phys(sel).intersected(pix.rect())
        return pix, origin, sx, sy, bounds

    def export_size(self, sel: QRect):
        return self._export_layout(sel)[-1].size()

    def export_selection(self, sel: QRect) -> NativeExport:
        """Export without recapture; single-monitor pixels are never resampled.

        Integer crop edges are rounded independently. The transform includes that
        rounding offset, rather than stretching the crop back to selection size.
        Synthetic callers replacing _shot deliberately use the legacy crop grid.
        """
        source, origin, sx, sy, bounds = self._export_layout(sel)
        native = (self._native_screens if self._shot.cacheKey()
                  == self._original_shot_key else [])
        if native and source is self._shot:
            source = QPixmap(self._shot.size())
            source.fill(QColor(0, 0, 0))
            p = QPainter(source)
            try:
                p.setRenderHint(QPainter.SmoothPixmapTransform, False)
                for geo, pix in native:
                    x0 = round((geo.x() - self._geo.x()) * sx)
                    y0 = round((geo.y() - self._geo.y()) * sy)
                    x1 = round((geo.x() + geo.width() - self._geo.x()) * sx)
                    y1 = round((geo.y() + geo.height() - self._geo.y()) * sy)
                    p.drawPixmap(QRect(x0, y0, x1 - x0, y1 - y0), pix, pix.rect())
            finally:
                p.end()
        elif not native:
            # Preserve old truncation semantics for tests/custom synthetic shots.
            bounds = self._to_phys(sel).intersected(source.rect())
        transform = QTransform(sx, 0, 0, sy,
                               -origin.x() * sx - bounds.x(),
                               -origin.y() * sy - bounds.y())
        return NativeExport(source.copy(bounds), transform, source, origin,
                            sx, sy, bounds)

    # ---------------------------------------------------- 手柄
    def _handle_points(self, sel: QRect) -> dict[str, QPoint]:
        cx, cy = sel.center().x(), sel.center().y()
        return {
            "tl": QPoint(sel.left(), sel.top()),
            "t": QPoint(cx, sel.top()),
            "tr": QPoint(sel.right(), sel.top()),
            "l": QPoint(sel.left(), cy),
            "r": QPoint(sel.right(), cy),
            "bl": QPoint(sel.left(), sel.bottom()),
            "b": QPoint(cx, sel.bottom()),
            "br": QPoint(sel.right(), sel.bottom()),
        }

    def _hit_handle(self, pos: QPoint) -> str | None:
        if not self._sel:
            return None
        for name, pt in self._handle_points(self._sel).items():
            if (abs(pos.x() - pt.x()) <= HANDLE // 2 + HIT_PAD
                    and abs(pos.y() - pt.y()) <= HANDLE // 2 + HIT_PAD):
                return name
        return None

    # ---------------------------------------------------- 绘制
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.drawPixmap(
            self.rect(), self._shot, QRect(0, 0, self._shot.width(), self._shot.height())
        )
        p.fillRect(self.rect(), QColor(0, 0, 0, 120))

        sel = self._sel
        if self._state == SELECTING and self._origin and self._current:
            sel = self._span_rect(self._origin, self._current)

        if sel is not None and sel.width() > 0 and sel.height() > 0:
            p.drawPixmap(sel, self._shot, self._to_phys(sel))
            p.setPen(QPen(QColor(0, 160, 255), 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawRect(sel)

            if self._state == READY and not (self.session and self.session.has_shapes()):
                p.setPen(QPen(QColor(0, 160, 255), 1))
                p.setBrush(QColor(255, 255, 255))
                half = HANDLE // 2
                for pt in self._handle_points(sel).values():
                    p.drawRect(QRect(pt.x() - half, pt.y() - half, HANDLE, HANDLE))

            self._draw_size_label(p, sel)

        if self._state == SELECTING and self._current:
            p.setPen(QPen(QColor(0, 160, 255, 110), 1, Qt.DashLine))
            p.drawLine(0, self._current.y(), self.width(), self._current.y())
            p.drawLine(self._current.x(), 0, self._current.x(), self.height())

        if self._state == READY and not self.panel.isVisible() and self.mode == MODE_TRANSLATE:
            self._draw_hint(p)

        if self.session is not None:
            self.session.paint(p)
        p.end()

    def _draw_hint(self, p: QPainter):
        hint = "拖动选区移动 · 拖手柄缩放 · Enter 重新识别 · Esc 关闭"
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 190))
        m = p.fontMetrics()
        tw = m.horizontalAdvance(hint) + 20
        th = m.height() + 8
        x = (self.width() - tw) // 2
        p.drawRoundedRect(QRect(x, 14, tw, th), 4, 4)
        p.setPen(QColor(210, 214, 220))
        p.drawText(QRect(x, 14, tw, th), Qt.AlignCenter, hint)

    def _draw_size_label(self, p: QPainter, sel: QRect):
        size = self.export_size(sel) if self.mode == MODE_SNIP else sel.size()
        label = f"{size.width()} × {size.height()}"
        m = p.fontMetrics()
        tw = m.horizontalAdvance(label) + 14
        th = m.height() + 6
        bx = sel.left()
        by = sel.top() - th - 6
        if by < 0:
            by = sel.bottom() + 6
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 200))
        p.drawRoundedRect(QRect(bx, by, tw, th), 4, 4)
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRect(bx, by, tw, th), Qt.AlignCenter, label)

    # ---------------------------------------------------- 面板定位
    def _place_panel(self):
        if not self._sel:
            self.panel.hide()
            return
        self.panel.adjustSize()
        pw, ph = self.panel.width(), self.panel.height()
        x = self._sel.center().x() - pw // 2
        y = self._sel.top() - ph - PANEL_GAP
        if y < 4:
            y = self._sel.bottom() + PANEL_GAP
        x = max(4, min(x, self.width() - pw - 4))
        y = max(4, min(y, self.height() - ph - 4))
        self.panel.move(x, y)
        self.panel.show()
        self.panel.raise_()

    def toggle_programmer_mode(self, enabled: bool):
        self.programmer_mode = enabled
        self.panel.btn_programmer.setChecked(enabled)
        if self.mode_changed:
            self.mode_changed(enabled)
        if self._sel:
            # 模式只影响翻译阶段，原文不变时不必重跑 OCR
            self._debounce.stop()
            if self._source_text:
                self.begin_result()
                self.panel.set_status("重新翻译…")
                self.retranslate_requested.emit(self._source_text)
            else:
                self.begin_result()
                self._emit_selection()

    def set_programmer_mode(self, enabled: bool):
        self.programmer_mode = bool(enabled)
        self.panel.btn_programmer.setChecked(self.programmer_mode)

    # ---------------------------------------------------- 结果区（供上层调用）
    def begin_result(self):
        """选区确定后立即调用：显示面板并进入"识别中"。"""
        self.panel.set_status("识别中…")
        self.panel.set_text("")
        self._place_panel()

    def show_source(self, text: str):
        self._source_text = text
        self.panel.set_status("翻译中…")
        self.panel.set_text(text)
        self._place_panel()

    def show_translation(self, text: str, notes=None):
        # notes 仅为兼容旧调用；标识符解释已由 ocr_engine 并入 text
        self._result_text = text
        self.panel.set_status("已翻译 · 代码模式" if self.programmer_mode else "已翻译")
        self.panel.set_text(text)
        self._place_panel()

    def show_message(self, msg: str):
        self.panel.set_status(msg)
        self.panel.set_text("")
        self._place_panel()

    # ---------------------------------------------------- 按钮动作
    def copy_result(self):
        from PySide6.QtWidgets import QApplication

        text = self._result_text or self._source_text
        if text:
            QApplication.clipboard().setText(text)
            self.panel.set_status("已复制译文")

    def copy_source(self):
        from PySide6.QtWidgets import QApplication

        if self._source_text:
            QApplication.clipboard().setText(self._source_text)
            self.panel.set_status("已复制原文")

    def redetect(self):
        if self._sel:
            self._debounce.stop()      # 取消待触发的防抖，避免重复 OCR
            self.begin_result()
            self._emit_selection()

    def _emit_selection(self):
        if self.mode != MODE_TRANSLATE:
            return
        if not self._sel or self._sel.width() < MIN_SIZE or self._sel.height() < MIN_SIZE:
            return
        self.selection_changed.emit(self._crop(self._sel), self._sel.translated(self._geo.topLeft()))

    def render_result(self) -> QPixmap:
        """返回当前选区成品：翻译模式是原图，Snip 模式已烘焙标注。"""
        if self._sel is None:
            return QPixmap()
        if self.session is not None:
            return self.session.finalize()
        return self._crop(self._sel)

    def set_selection(self, sel: QRect):
        """外部（窗口识别）直接指定选区。"""
        r = sel.intersected(QRect(0, 0, self.width(), self.height()))
        if r.width() < MIN_SIZE or r.height() < MIN_SIZE:
            return
        self._sel = r
        self._state = READY
        self.setCursor(Qt.SizeAllCursor)
        self.update()

    # ---------------------------------------------------- 生命周期
    def close_all(self):
        self.close()

    def closeEvent(self, event):
        if not self._closed:
            self._closed = True
            self._debounce.stop()
            self.panel.hide()
            if self.session is not None:
                self.session.cleanup()
            self._shot = QPixmap()
            self._native_screens.clear()
            self.closed.emit()
        event.accept()

    def reset_selection(self):
        self._debounce.stop()
        self._state = IDLE
        self._sel = None
        self._origin = self._current = None
        self.panel.hide()
        if self.session is not None:
            self.session.on_selection_cleared()
        self.setCursor(self.capture_cursor)
        self.update()

    # ---------------------------------------------------- 交互
    def mousePressEvent(self, e):
        pos = e.position().toPoint()

        if self.session is not None and self.session.handle_press(e, pos):
            return

        if e.button() == Qt.RightButton:
            self.close_all()
            return
        if e.button() != Qt.LeftButton:
            return

        if self._state == READY and self._sel:
            handle = self._hit_handle(pos)
            if handle:
                self._drag_mode, self._drag_handle = "resize", handle
                self._drag_start, self._drag_rect = pos, QRect(self._sel)
                return
            if self._sel.contains(pos):
                self._drag_mode, self._drag_handle = "move", None
                self._drag_start, self._drag_rect = pos, QRect(self._sel)
                self.setCursor(Qt.SizeAllCursor)
                return
            # 点在选区和面板之外 → 关闭整个翻译层
            self.close_all()
            return

        self._state = SELECTING
        self._origin = self._current = pos
        self.panel.hide()
        self._debounce.stop()
        self.update()

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()

        if self.session is not None and self.session.handle_move(e, pos):
            return

        if self._state == SELECTING:
            self._current = pos
            self.update()
            return

        if self._drag_mode == "move" and self._sel:
            delta = pos - self._drag_start
            moved = self._drag_rect.translated(delta)
            moved.moveLeft(max(0, min(moved.left(), self.width() - moved.width())))
            moved.moveTop(max(0, min(moved.top(), self.height() - moved.height())))
            old = self._sel
            self._sel = moved
            if self.session is not None:
                self.session.model.translate(
                    moved.left() - old.left(), moved.top() - old.top()
                )
            if self.panel.isVisible():
                self._place_panel()
            if self.session is not None:
                self.session.place_toolbar()
            self.update()
            return

        if self._drag_mode == "resize" and self._sel:
            self._resize_to(pos)
            if self.panel.isVisible():
                self._place_panel()
            if self.session is not None:
                self.session.place_toolbar()
            self.update()
            return

        if self._state == READY:
            cursors = {
                "tl": Qt.SizeFDiagCursor, "br": Qt.SizeFDiagCursor,
                "tr": Qt.SizeBDiagCursor, "bl": Qt.SizeBDiagCursor,
                "t": Qt.SizeVerCursor, "b": Qt.SizeVerCursor,
                "l": Qt.SizeHorCursor, "r": Qt.SizeHorCursor,
            }
            h = self._hit_handle(pos)
            if h:
                self.setCursor(cursors[h])
            elif self._sel and self._sel.contains(pos):
                self.setCursor(Qt.SizeAllCursor)
            else:
                self.setCursor(self.capture_cursor)

    def _resize_to(self, pos: QPoint):
        r = QRect(self._drag_rect)
        h = self._drag_handle
        if "l" in h:
            r.setLeft(min(pos.x(), r.right() - MIN_SIZE))
        if "r" in h:
            r.setRight(max(pos.x(), r.left() + MIN_SIZE))
        if "t" in h:
            r.setTop(min(pos.y(), r.bottom() - MIN_SIZE))
        if "b" in h:
            r.setBottom(max(pos.y(), r.top() + MIN_SIZE))
        r.setLeft(max(0, r.left()))
        r.setTop(max(0, r.top()))
        r.setRight(min(self.width() - 1, r.right()))
        r.setBottom(min(self.height() - 1, r.bottom()))
        self._sel = r

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton:
            return

        if self.session is not None and self.session.handle_release(
            e, e.position().toPoint()
        ):
            return

        if self._state == SELECTING:
            sel = self._span_rect(self._origin, e.position().toPoint())
            self._origin = self._current = None
            if sel.width() < MIN_SIZE or sel.height() < MIN_SIZE:
                self.reset_selection()
                return
            self._sel = sel
            self._state = READY
            self.setCursor(Qt.SizeAllCursor)
            if self.session is not None:
                self.session.after_selection()
            else:
                self.begin_result()
                # 首次框选不需要防抖：立即识别，避免白等 280ms
                self._emit_selection()
            self.update()
            return

        if self._drag_mode:
            self._drag_mode = self._drag_handle = None
            self.setCursor(QCursor(Qt.SizeAllCursor) if self._sel else self.capture_cursor)
            if self._sel:
                if self.session is not None:
                    self.session.on_selection_changed()
                else:
                    self.begin_result()
                    self._debounce.start()   # 松手后重新识别
            self.update()

    def mouseDoubleClickEvent(self, e):
        if self.session is not None and self.session.handle_double_click(
            e, e.position().toPoint()
        ):
            return
        if e.button() == Qt.LeftButton and self._state == READY:
            self.redetect()

    def keyPressEvent(self, e):
        if self.session is not None and self.session.handle_key(e):
            return
        if e.key() == Qt.Key_Escape:
            self.close_all()
        elif e.key() in (Qt.Key_Return, Qt.Key_Enter) and self._state == READY:
            self.redetect()

    def focusNextPrevChild(self, next_widget):
        # Snip 模式的 Tab 用于窗口识别，不能被 Qt 的焦点遍历吞掉
        if self.session is not None:
            return False
        return super().focusNextPrevChild(next_widget)
