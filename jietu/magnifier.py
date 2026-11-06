"""取色放大镜：最近邻放大、像素网格、坐标与 HEX/RGB。"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen


CELLS = 14          # 放大区域覆盖的逻辑像素数
ZOOM = 8            # 每个源像素放大后的逻辑尺寸
INFO_H = 24


def sample_color(image: QImage, phys_point: QPoint) -> QColor:
    if image is None or image.isNull():
        return QColor(0, 0, 0)
    x = min(max(0, phys_point.x()), image.width() - 1)
    y = min(max(0, phys_point.y()), image.height() - 1)
    return image.pixelColor(x, y)


def paint_magnifier(p: QPainter, image: QImage, phys_point: QPoint, scale: float,
                    cursor_local: QPoint, bounds: QSize, global_point: QPoint):
    if image is None or image.isNull():
        return

    side_phys = max(1, int(round(CELLS * scale)))
    half = side_phys // 2
    src = QRect(phys_point.x() - half, phys_point.y() - half, side_phys, side_phys)
    src = src.intersected(image.rect())
    if src.isEmpty():
        return

    box = max(CELLS * ZOOM, 300)
    margin = 18
    x = cursor_local.x() + margin
    y = cursor_local.y() + margin
    if x + box + 2 > bounds.width():
        x = cursor_local.x() - box - margin
    if y + box + INFO_H + 2 > bounds.height():
        y = cursor_local.y() - box - INFO_H - margin
    x = max(2, x)
    y = max(2, y)

    p.save()
    p.setRenderHint(QPainter.SmoothPixmapTransform, False)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(24, 26, 30, 238))
    p.drawRoundedRect(QRect(x - 3, y - 3, box + 6, box + INFO_H + 6), 5, 5)

    target = QRect(x, y, box, box)
    p.drawImage(target, image, src)

    # 网格线
    cols = max(1, src.width())
    rows = max(1, src.height())
    cw = box / cols
    ch = box / rows
    p.setPen(QPen(QColor(255, 255, 255, 34), 1))
    for i in range(cols + 1):
        gx = int(x + i * cw)
        p.drawLine(gx, y, gx, y + box)
    for j in range(rows + 1):
        gy = int(y + j * ch)
        p.drawLine(x, gy, x + box, gy)

    # 当前像素高亮
    cx = phys_point.x() - src.left()
    cy = phys_point.y() - src.top()
    if 0 <= cx < cols and 0 <= cy < rows:
        p.setPen(QPen(QColor(232, 80, 58), 2))
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRect(int(x + cx * cw), int(y + cy * ch),
                         max(2, int(cw)), max(2, int(ch))))

    # 信息条
    color = sample_color(image, phys_point)
    hexv = color.name().upper()
    text = f"{global_point.x()},{global_point.y()}  {hexv}  ({color.red()},{color.green()},{color.blue()})"
    info = QRect(x, y + box + 2, box, INFO_H)
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    p.drawRect(QRect(info.x() + 3, info.y() + 4, 16, INFO_H - 8))
    p.setPen(QColor(230, 233, 238))
    p.drawText(info.adjusted(24, 0, -2, 0), Qt.AlignVCenter | Qt.AlignLeft, text)
    p.restore()
