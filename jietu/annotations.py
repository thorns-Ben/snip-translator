"""标注图形模型、命中测试与渲染。

坐标约定：
  * Shape.points 一律保存「覆盖层本地逻辑坐标」。
  * 渲染时通过 (逻辑点 - origin) * scale 映射到源图物理像素，
    因此同一套图形可以画在实时覆盖层（origin=0）和最终裁剪图上
    （origin=选区左上角），预览与产物完全一致。
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass, field

from PySide6.QtCore import QBuffer, QIODevice, QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QImage,
    QPainter,
    QPen,
    QPolygonF,
)

RECT_KINDS = ("rect", "ellipse", "mosaic", "blur")
LINE_KINDS = ("line", "arrow")
FREE_KINDS = ("pen", "highlighter")


@dataclass
class Shape:
    kind: str
    points: list[QPointF]
    color: QColor
    width: float
    text: str = ""
    font_size: float = 16.0
    _cache: QImage | None = field(default=None, repr=False, compare=False)
    _cache_key: tuple = field(default=(), repr=False, compare=False)


def _font(shape: Shape) -> QFont:
    f = QFont()
    f.setPixelSize(max(6, int(round(shape.font_size))))
    return f


def _points_rect(points: list[QPointF]) -> QRectF:
    if not points:
        return QRectF()
    x0 = min(p.x() for p in points)
    y0 = min(p.y() for p in points)
    x1 = max(p.x() for p in points)
    y1 = max(p.y() for p in points)
    return QRectF(x0, y0, max(0.5, x1 - x0), max(0.5, y1 - y0))


def shape_rect(shape: Shape) -> QRectF:
    """图形的逻辑包围盒（用于橡皮擦命中、效果区域、剪裁）。"""
    if shape.kind == "text":
        if not shape.points:
            return QRectF()
        lines = shape.text.splitlines() or [""]
        fm = QFontMetricsF(_font(shape))
        w = max((fm.horizontalAdvance(line) for line in lines), default=8)
        h = fm.height() * max(1, len(lines))
        return QRectF(shape.points[0].x(), shape.points[0].y(), max(w, 8), max(h, 8)).normalized()
    r = _points_rect(shape.points)
    if shape.width > 1:
        pad = shape.width / 2.0
        r = r.adjusted(-pad, -pad, pad, pad)
    return r


def _qimage_to_pil(img: QImage):
    from PIL import Image

    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    data = bytes(buf.data())
    buf.close()
    return Image.open(io.BytesIO(data)).convert("RGB")


def _pil_to_qimage(pil) -> QImage:
    buf = io.BytesIO()
    pil.save(buf, "PNG")
    return QImage.fromData(buf.getvalue(), "PNG")


def _effect_image(shape: Shape, source: QImage, origin: QPointF, scale: float | tuple[float, float]) -> QImage | None:
    """按源图物理像素生成马赛克/模糊结果，带缓存。"""
    if source is None or source.isNull():
        return None
    r = shape_rect(shape)
    if r.isEmpty():
        return None
    sx, sy = scale if isinstance(scale, tuple) else (scale, scale)
    key = (
        source.cacheKey(), origin.x(), origin.y(), sx, sy,
        shape.kind,
        round(r.x(), 2), round(r.y(), 2),
        round(r.width(), 2), round(r.height(), 2),
        round(shape.width, 2),
    )
    if shape._cache is not None and shape._cache_key == key:
        return shape._cache

    phys = QRectF(
        (r.x() - origin.x()) * sx,
        (r.y() - origin.y()) * sy,
        max(1.0, r.width() * sx),
        max(1.0, r.height() * sy),
    ).toAlignedRect().intersected(QRectF(source.rect()).toRect())
    if phys.isEmpty():
        return None

    crop = source.copy(phys)
    scale = (sx + sy) / 2.0
    if shape.kind == "mosaic":
        block = max(2, int(round(shape.width * scale / 2)))
        sw = max(1, crop.width() // block)
        sh = max(1, crop.height() // block)
        small = crop.scaled(sw, sh, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        out = small.scaled(crop.width(), crop.height(),
                           Qt.IgnoreAspectRatio, Qt.FastTransformation)
    else:
        from PIL import ImageFilter

        radius = max(1.0, shape.width * scale / 3.0)
        try:
            out = _pil_to_qimage(_qimage_to_pil(crop).filter(ImageFilter.GaussianBlur(radius)))
        except Exception:
            out = crop

    shape._cache = out
    shape._cache_key = key
    return out


def _arrow_head(start: QPointF, end: QPointF, width: float) -> QPolygonF:
    dx = end.x() - start.x()
    dy = end.y() - start.y()
    length = math.hypot(dx, dy)
    if length < 1e-3:
        return QPolygonF()
    ang = math.atan2(dy, dx)
    head = max(9.0, width * 4.0)
    spread = math.radians(26)
    p1 = QPointF(end.x() - head * math.cos(ang - spread),
                 end.y() - head * math.sin(ang - spread))
    p2 = QPointF(end.x() - head * math.cos(ang + spread),
                 end.y() - head * math.sin(ang + spread))
    return QPolygonF([end, p1, p2])


def draw_shape(p: QPainter, shape: Shape, source: QImage | None,
               origin: QPointF, scale: float | tuple[float, float]):
    pts = shape.points
    if not pts:
        return

    if shape.kind in ("rect", "ellipse"):
        if len(pts) < 2:
            return
        r = QRectF(pts[0], pts[1]).normalized()
        p.setPen(QPen(shape.color, shape.width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        if shape.kind == "rect":
            p.drawRect(r)
        else:
            p.drawEllipse(r)
        return

    if shape.kind in LINE_KINDS:
        if len(pts) < 2:
            return
        p.setPen(QPen(shape.color, shape.width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        p.drawLine(pts[0], pts[-1])
        if shape.kind == "arrow":
            head = _arrow_head(pts[0], pts[-1], shape.width)
            if not head.isEmpty():
                p.setPen(Qt.NoPen)
                p.setBrush(shape.color)
                p.drawPolygon(head)
        return

    if shape.kind in FREE_KINDS:
        color = QColor(shape.color)
        width = shape.width
        if shape.kind == "highlighter":
            color.setAlpha(90)
            width = width * 3.0
        pen = QPen(color, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        if len(pts) == 1:
            p.drawPoint(pts[0])
        else:
            p.drawPolyline(QPolygonF(pts))
        return

    if shape.kind == "text":
        p.setPen(shape.color)
        p.setFont(_font(shape))
        p.setBrush(Qt.NoBrush)
        rect = QRectF(pts[0].x(), pts[0].y(), 4000, 4000)
        p.drawText(rect, Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, shape.text)
        return

    if shape.kind in ("mosaic", "blur"):
        r = shape_rect(shape)
        if r.isEmpty():
            return
        img = _effect_image(shape, source, origin, scale) if source is not None else None
        if img is not None:
            sx, sy = scale if isinstance(scale, tuple) else (scale, scale)
            phys = QRectF((r.x() - origin.x()) * sx,
                          (r.y() - origin.y()) * sy,
                          max(1.0, r.width() * sx),
                          max(1.0, r.height() * sy)).toAlignedRect()
            phys = phys.intersected(source.rect())
            target = QRectF(origin.x() + phys.x() / sx,
                            origin.y() + phys.y() / sy,
                            phys.width() / sx, phys.height() / sy)
            p.drawImage(target, img)
        return


def draw_shapes(p: QPainter, shapes: list[Shape], source: QImage | None,
                origin: QPointF, scale: float | tuple[float, float]):
    for sh in shapes:
        draw_shape(p, sh, source, origin, scale)


def translate_shapes(shapes: list[Shape], dx: float, dy: float):
    d = QPointF(dx, dy)
    for sh in shapes:
        sh.points = [pt + d for pt in sh.points]
        sh._cache_key = ()


class AnnotationModel(QObject):
    """图形栈 + 撤销/重做。"""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._shapes: list[Shape] = []
        self._undo: list[tuple] = []
        self._redo: list[tuple] = []

    def shapes(self) -> list[Shape]:
        return list(self._shapes)

    def __len__(self) -> int:
        return len(self._shapes)

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def add(self, shape: Shape):
        self._shapes.append(shape)
        self._undo.append(("add", shape, len(self._shapes) - 1))
        self._redo.clear()
        self.changed.emit()

    def remove_at(self, pos: QPointF, tol: float = 4.0) -> bool:
        for idx in range(len(self._shapes) - 1, -1, -1):
            sh = self._shapes[idx]
            if shape_rect(sh).adjusted(-tol, -tol, tol, tol).contains(pos):
                del self._shapes[idx]
                self._undo.append(("remove", sh, idx))
                self._redo.clear()
                self.changed.emit()
                return True
        return False

    def undo(self) -> bool:
        if not self._undo:
            return False
        op = self._undo.pop()
        kind, shape, idx = op
        if kind == "add":
            if shape in self._shapes:
                self._shapes.remove(shape)
        else:
            self._shapes.insert(min(idx, len(self._shapes)), shape)
        self._redo.append(op)
        self.changed.emit()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        op = self._redo.pop()
        kind, shape, idx = op
        if kind == "add":
            self._shapes.insert(min(idx, len(self._shapes)), shape)
        else:
            if shape in self._shapes:
                self._shapes.remove(shape)
        self._undo.append(op)
        self.changed.emit()
        return True

    def translate(self, dx: float, dy: float):
        shapes = {id(shape): shape for shape in self._shapes}
        for _, shape, _ in self._undo + self._redo:
            shapes[id(shape)] = shape
        translate_shapes(list(shapes.values()), dx, dy)

    def clear(self):
        if not self._shapes:
            return
        self._shapes.clear()
        self._undo.clear()
        self._redo.clear()
        self.changed.emit()
