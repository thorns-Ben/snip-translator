"""Snipaste 式标注工具栏（覆盖层子控件，纯程序化图标）。"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QButtonGroup,
    QColorDialog,
    QFrame,
    QHBoxLayout,
    QMenu,
    QToolButton,
    QWidget,
)

TOOLS = [
    ("rect", "矩形"),
    ("ellipse", "椭圆"),
    ("line", "直线"),
    ("arrow", "箭头"),
    ("pen", "画笔"),
    ("highlighter", "荧光笔"),
    ("text", "文字"),
    ("mosaic", "马赛克"),
    ("blur", "模糊"),
    ("eraser", "橡皮擦"),
]

COLORS = ["#e8503a", "#f5c542", "#4cd964", "#3aa0ff", "#b45cff", "#ffffff", "#000000"]
WIDTHS = [1, 2, 3, 4, 6, 8]

_ICON = QColor("#d5d9df")


def _pix(kind: str, color: QColor | None = None, width: float = 1.6) -> QPixmap:
    pm = QPixmap(20, 20)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(color or _ICON, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)

    if kind == "rect":
        p.drawRect(3, 4, 14, 12)
    elif kind == "ellipse":
        p.drawEllipse(3, 4, 14, 12)
    elif kind == "line":
        p.drawLine(3, 16, 17, 4)
    elif kind == "arrow":
        p.drawLine(3, 16, 16, 4)
        p.setBrush(pen.color())
        p.drawPolygon(QPolygonF([QPointF(16, 4), QPointF(9, 5), QPointF(15, 11)]))
    elif kind == "pen":
        p.drawLine(4, 16, 14, 6)
        p.setBrush(pen.color())
        p.drawPolygon(QPolygonF([QPointF(4, 16), QPointF(7.5, 15.5), QPointF(4.5, 12.5)]))
    elif kind == "highlighter":
        pen.setWidthF(6)
        pen.setColor(QColor("#f5c542"))
        p.setPen(pen)
        p.drawLine(4, 15, 15, 7)
    elif kind == "text":
        f = QFont()
        f.setPixelSize(15)
        f.setBold(True)
        p.setFont(f)
        p.drawText(pm.rect(), Qt.AlignCenter, "T")
    elif kind == "mosaic":
        for i in range(4):
            for j in range(4):
                if (i + j) % 2 == 0:
                    p.fillRect(QRectF(3 + i * 3.5, 4 + j * 3.5, 3, 3), pen.color())
    elif kind == "blur":
        p.drawEllipse(4, 4, 12, 12)
        p.setPen(QPen(pen.color(), 1, Qt.DotLine))
        p.drawEllipse(7, 7, 6, 6)
    elif kind == "eraser":
        p.save()
        p.translate(10, 10)
        p.rotate(-35)
        p.drawRoundedRect(-6, -4, 12, 8, 2, 2)
        p.restore()
    elif kind in ("undo", "redo"):
        p.drawArc(4, 6, 12, 10, 30 * 16, 300 * 16)
        p.setBrush(pen.color())
        if kind == "undo":
            p.drawPolygon(QPolygonF([QPointF(4, 4), QPointF(4, 11), QPointF(9, 7)]))
        else:
            p.drawPolygon(QPolygonF([QPointF(16, 4), QPointF(16, 11), QPointF(11, 7)]))
    elif kind == "pin":
        p.drawEllipse(5, 3, 10, 10)
        p.drawLine(10, 13, 10, 18)
    elif kind == "copy":
        p.drawRect(3, 3, 10, 10)
        p.drawRect(7, 7, 10, 10)
    elif kind == "save":
        p.drawRect(3, 3, 14, 14)
        p.drawRect(7, 3, 6, 5)
        p.drawRect(6, 11, 8, 6)
    elif kind == "close":
        p.drawLine(4, 4, 16, 16)
        p.drawLine(16, 4, 4, 16)
    p.end()
    return pm


def place_near_selection(widget: QWidget, sel: QRect, gap: int, bounds: QSize):
    widget.adjustSize()
    w, h = widget.width(), widget.height()
    x = sel.center().x() - w // 2
    y = sel.bottom() + gap
    if y + h + 4 > bounds.height():
        y = sel.top() - h - gap
    if y < 4:
        y = max(4, min(sel.bottom() + gap, bounds.height() - h - 4))
    x = max(4, min(x, bounds.width() - w - 4))
    widget.move(x, y)
    widget.show()
    widget.raise_()


class AnnoToolbar(QWidget):
    tool_changed = Signal(object)      # str | None
    undo_clicked = Signal()
    redo_clicked = Signal()
    color_changed = Signal(QColor)
    width_changed = Signal(int)
    copy_clicked = Signal()
    save_clicked = Signal()
    pin_clicked = Signal()
    close_clicked = Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("annoToolbar")
        self.setAutoFillBackground(True)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.NoFocus)

        self._color = QColor(COLORS[0])
        self._width = 3
        self._active: str | None = None
        self._buttons: dict[str, QToolButton] = {}

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 5, 6, 5)
        lay.setSpacing(2)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for key, name in TOOLS:
            b = self._icon_button(_pix(key), name, checkable=True)
            b.clicked.connect(lambda _=False, k=key: self._click_tool(k))
            self._group.addButton(b)
            self._buttons[key] = b
            lay.addWidget(b)

        lay.addWidget(self._sep())
        self.btn_undo = self._icon_button(_pix("undo"), "撤销 (Ctrl+Z)")
        self.btn_redo = self._icon_button(_pix("redo"), "重做 (Ctrl+Y)")
        self.btn_undo.clicked.connect(self.undo_clicked)
        self.btn_redo.clicked.connect(self.redo_clicked)
        lay.addWidget(self.btn_undo)
        lay.addWidget(self.btn_redo)

        lay.addWidget(self._sep())
        self.btn_color = self._icon_button(self._swatch(self._color), "颜色")
        self.btn_width = self._icon_button(self._width_pix(self._width), "线宽")
        self.btn_color.clicked.connect(self._pick_color)
        self.btn_width.clicked.connect(self._pick_width)
        lay.addWidget(self.btn_color)
        lay.addWidget(self.btn_width)

        lay.addWidget(self._sep())
        b_pin = self._icon_button(_pix("pin"), "贴图 (F3)")
        b_copy = self._icon_button(_pix("copy"), "复制图片 (Ctrl+C)")
        b_save = self._icon_button(_pix("save"), "保存 PNG (Ctrl+S)")
        b_close = self._icon_button(_pix("close"), "关闭 (Esc)")
        b_pin.clicked.connect(self.pin_clicked)
        b_copy.clicked.connect(self.copy_clicked)
        b_save.clicked.connect(self.save_clicked)
        b_close.clicked.connect(self.close_clicked)
        for b in (b_pin, b_copy, b_save, b_close):
            lay.addWidget(b)

        self.setStyleSheet("""
            #annoToolbar { background: #26292e; border: 1px solid #4b5059;
                           border-radius: 8px; }
            QToolButton { background: transparent; border: none; border-radius: 4px; }
            QToolButton:hover { background: #3a3e46; }
            QToolButton:checked { background: #e8503a; }
            QToolButton:disabled { opacity: 0.35; }
            #annoSep { background: #3f434b; max-width: 1px; min-width: 1px; }
        """)
        self.btn_undo.setEnabled(False)
        self.btn_redo.setEnabled(False)

    # -------------------------------------------------- 构造辅助
    def _icon_button(self, pm: QPixmap, tip: str, checkable=False) -> QToolButton:
        b = QToolButton(self)
        b.setIcon(QIcon(pm))
        b.setIconSize(QSize(20, 20))
        b.setFixedSize(28, 28)
        b.setToolTip(tip)
        b.setCheckable(checkable)
        b.setCursor(Qt.PointingHandCursor)
        b.setAutoRaise(True)
        b.setFocusPolicy(Qt.NoFocus)
        return b

    def _sep(self) -> QFrame:
        f = QFrame(self)
        f.setObjectName("annoSep")
        f.setFrameShape(QFrame.VLine)
        f.setFixedHeight(20)
        return f

    @staticmethod
    def _swatch(color: QColor) -> QPixmap:
        pm = QPixmap(20, 20)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor("#8a9099"), 1))
        p.setBrush(color)
        p.drawRoundedRect(3, 3, 14, 14, 3, 3)
        p.end()
        return pm

    @staticmethod
    def _width_pix(width: int) -> QPixmap:
        pm = QPixmap(20, 20)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setPen(QPen(_ICON, max(1, width), Qt.SolidLine, Qt.RoundCap))
        p.drawLine(3, 10, 17, 10)
        p.end()
        return pm

    def mousePressEvent(self, event):
        event.accept()

    def mouseReleaseEvent(self, event):
        event.accept()

    def mouseDoubleClickEvent(self, event):
        event.accept()

    # -------------------------------------------------- 状态
    def current_color(self) -> QColor:
        return QColor(self._color)

    def current_width(self) -> int:
        return self._width

    def active_tool(self) -> str | None:
        return self._active

    def set_active_tool(self, tool: str | None):
        self._active = tool
        self._group.setExclusive(False)
        for key, b in self._buttons.items():
            b.setChecked(key == tool)
        self._group.setExclusive(True)

    def set_undo_enabled(self, on: bool):
        self.btn_undo.setEnabled(on)

    def set_redo_enabled(self, on: bool):
        self.btn_redo.setEnabled(on)

    # -------------------------------------------------- 交互
    def _click_tool(self, key: str):
        if self._active == key:
            self.set_active_tool(None)
        else:
            self.set_active_tool(key)
        self.tool_changed.emit(self._active)

    def _pick_color(self):
        menu = QMenu(self)
        for c in COLORS:
            act = menu.addAction(QIcon(self._swatch(QColor(c))), c.upper())
            act.triggered.connect(lambda _=False, col=c: self._set_color(QColor(col)))
        menu.addSeparator()
        act_custom = menu.addAction("自定义…")
        act_custom.triggered.connect(self._custom_color)
        menu.exec(self.btn_color.mapToGlobal(QPoint(0, self.btn_color.height())))

    def _set_color(self, color: QColor):
        self._color = QColor(color)
        self.btn_color.setIcon(QIcon(self._swatch(self._color)))
        self.color_changed.emit(QColor(self._color))

    def _custom_color(self):
        c = QColorDialog.getColor(self._color, self, "选择颜色")
        if c.isValid():
            self._set_color(c)

    def _pick_width(self):
        menu = QMenu(self)
        for w in WIDTHS:
            act = menu.addAction(QIcon(self._width_pix(w)), f"{w} px")
            act.triggered.connect(lambda _=False, v=w: self._set_width(v))
        menu.exec(self.btn_width.mapToGlobal(QPoint(0, self.btn_width.height())))

    def _set_width(self, width: int):
        self._width = width
        self.btn_width.setIcon(QIcon(self._width_pix(width)))
        self.width_changed.emit(width)
