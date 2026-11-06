"""Snipaste 式贴图窗口：置顶、拖动、缩放、透明度、旋转翻转、鼠标穿透。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QPoint, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QGuiApplication,
    QImage,
    QPainter,
    QPixmap,
    QTransform,
)
from PySide6.QtWidgets import QFileDialog, QMenu, QMessageBox, QWidget

from .paths import default_save_dir, save_pixmap, unique_png_path


class PinWindow(QWidget):
    closed = Signal(object)

    def __init__(self, pixmap: QPixmap, logical_size: QSize, pos: QPoint,
                 save_dir=None, manager=None):
        super().__init__(None)
        self.setWindowFlags(
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
            | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle("贴图")
        self.setMouseTracking(True)

        self._manager = manager
        self.save_dir = Path(save_dir or default_save_dir())
        self._base = QPixmap(pixmap)
        lw = max(1, logical_size.width())
        self._dpr = max(1.0, self._base.width() / lw)
        self._base.setDevicePixelRatio(self._dpr)

        self._zoom = 1.0
        self._opacity = 1.0
        self._rot = 0
        self._flip_h = False
        self._flip_v = False
        self._through = False
        self._closed = False
        self._press: QPoint | None = None
        self._press_pos = QPoint()

        self._display = QPixmap(self._base)
        self._rebuild()
        self.move(pos)
        self.show()
        self.raise_()

    # -------------------------------------------------- 显示
    def _rebuild(self):
        img = self._base.toImage()
        img.setDevicePixelRatio(1.0)
        if self._flip_h or self._flip_v:
            img = img.mirrored(self._flip_h, self._flip_v)
        if self._rot % 360:
            img = img.transformed(QTransform().rotate(self._rot))
        pm = QPixmap.fromImage(img)
        pm.setDevicePixelRatio(self._dpr)
        self._display = pm
        self._resize_display()

    def _resize_display(self):
        w = max(1, int(round(self._display.width() / self._dpr * self._zoom)))
        h = max(1, int(round(self._display.height() / self._dpr * self._zoom)))
        self.resize(w, h)
        self.setWindowOpacity(self._opacity)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.drawPixmap(self.rect(), self._display)
        p.setPen(QColor(255, 255, 255, 36))
        p.setBrush(Qt.NoBrush)
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        p.end()

    # -------------------------------------------------- 交互
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press = e.globalPosition().toPoint()
            self._press_pos = self.pos()
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, e):
        if self._press is not None and (e.buttons() & Qt.LeftButton):
            delta = e.globalPosition().toPoint() - self._press
            self.move(self._press_pos + delta)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press = None
            self.setCursor(Qt.ArrowCursor)

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.close()

    def wheelEvent(self, e):
        delta = e.angleDelta().y()
        if not delta:
            return
        if e.modifiers() & Qt.ControlModifier:
            step = 0.05 if delta > 0 else -0.05
            self._opacity = min(1.0, max(0.1, self._opacity + step))
        else:
            factor = 1.1 if delta > 0 else 1 / 1.1
            self._zoom = min(8.0, max(0.1, self._zoom * factor))
        self._resize_display()
        e.accept()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.close()
        elif e.key() == Qt.Key_C and e.modifiers() & Qt.ControlModifier:
            self.copy_image()
        elif e.key() == Qt.Key_S and e.modifiers() & Qt.ControlModifier:
            self.save_as()
        else:
            super().keyPressEvent(e)

    def contextMenuEvent(self, e):
        menu = QMenu(self)
        act_copy = menu.addAction("复制图片 (Ctrl+C)")
        act_save = menu.addAction("另存为 (Ctrl+S)")
        menu.addSeparator()
        act_rot = menu.addAction("旋转 90°")
        act_fh = menu.addAction("水平翻转")
        act_fv = menu.addAction("垂直翻转")

        op_menu = menu.addMenu("不透明度")
        op_acts = []
        for pct in (100, 90, 80, 70, 60, 50, 40, 30, 20, 10):
            a = op_menu.addAction(f"{pct}%")
            a.setCheckable(True)
            a.setChecked(abs(self._opacity * 100 - pct) < 1)
            a.triggered.connect(lambda _=False, v=pct: self._set_opacity(v / 100.0))
            op_acts.append(a)

        act_through = menu.addAction("鼠标穿透")
        act_through.setCheckable(True)
        act_through.setChecked(self._through)
        menu.addSeparator()
        act_close = menu.addAction("关闭贴图 (Esc)")
        act_all = menu.addAction("关闭全部贴图")

        chosen = menu.exec(e.globalPos())
        if chosen is act_copy:
            self.copy_image()
        elif chosen is act_save:
            self.save_as()
        elif chosen is act_rot:
            self._rot = (self._rot + 90) % 360
            self._rebuild()
        elif chosen is act_fh:
            self._flip_h = not self._flip_h
            self._rebuild()
        elif chosen is act_fv:
            self._flip_v = not self._flip_v
            self._rebuild()
        elif chosen is act_through:
            self.set_mouse_through(not self._through)
        elif chosen is act_close:
            self.close()
        elif chosen is act_all and self._manager is not None:
            self._manager.close_all()

    # -------------------------------------------------- 动作
    def _set_opacity(self, value: float):
        self._opacity = min(1.0, max(0.1, value))
        self.setWindowOpacity(self._opacity)

    def set_mouse_through(self, on: bool):
        if self._through == on:
            return
        self._through = on
        self.setWindowFlag(Qt.WindowTransparentForInput, on)
        self.show()
        self.raise_()
        if self._manager is not None:
            self._manager.changed.emit()

    def copy_image(self):
        QGuiApplication.clipboard().setPixmap(self._display)

    def save_as(self):
        start = str(self.save_dir / "pin.png")
        path, _ = QFileDialog.getSaveFileName(self, "另存为", start, "PNG (*.png)")
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        try:
            save_pixmap(self._display, path)
        except Exception as exc:
            QMessageBox.warning(self, "保存失败", str(exc))

    def save_quick(self) -> Path | None:
        try:
            return save_pixmap(self._display, unique_png_path(self.save_dir))
        except Exception as exc:
            QMessageBox.warning(self, "保存失败", str(exc))
            return None

    def closeEvent(self, e):
        if not self._closed:
            self._closed = True
            self.closed.emit(self)
        super().closeEvent(e)


class PinManager(QObject):
    """持有所有贴图窗口的强引用，避免被 Python GC 回收。"""

    changed = Signal()

    def __init__(self, save_dir=None, parent=None):
        super().__init__(parent)
        self.save_dir = Path(save_dir or default_save_dir())
        self._pins: list[PinWindow] = []

    def all(self) -> list[PinWindow]:
        return list(self._pins)

    def create(self, pixmap: QPixmap, logical_size: QSize, pos: QPoint | None = None) -> PinWindow:
        if pos is None:
            pos = QCursor.pos()
        pos = self._clamp(pos, logical_size)
        pin = PinWindow(pixmap, logical_size, pos,
                        save_dir=self.save_dir, manager=self)
        self._pins.append(pin)
        pin.closed.connect(self._on_closed)
        self.changed.emit()
        return pin

    def create_from_clipboard(self) -> PinWindow | None:
        cb = QGuiApplication.clipboard()
        img = cb.image()
        if img.isNull():
            md = cb.mimeData()
            if md is not None and md.hasImage():
                data = md.imageData()
                if isinstance(data, QImage):
                    img = data
        if img.isNull() or img.width() == 0:
            return None
        pm = QPixmap.fromImage(img)
        logical = QSize(
            max(1, int(round(img.width() / max(1.0, img.devicePixelRatio())))),
            max(1, int(round(img.height() / max(1.0, img.devicePixelRatio())))),
        )
        return self.create(pm, logical, QCursor.pos())

    def _clamp(self, pos: QPoint, size: QSize) -> QPoint:
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        if screen is None:
            return pos
        a = screen.availableGeometry()
        x = min(max(pos.x(), a.left()), max(a.left(), a.right() - size.width() + 1))
        y = min(max(pos.y(), a.top()), max(a.top(), a.bottom() - size.height() + 1))
        return QPoint(x, y)

    def hide_all(self):
        for pin in self._pins:
            pin.hide()

    def show_all(self):
        for pin in self._pins:
            pin.show()
            pin.raise_()

    def set_mouse_through_all(self, on: bool):
        for pin in self._pins:
            pin.set_mouse_through(on)
        self.changed.emit()

    def close_all(self):
        for pin in list(self._pins):
            pin.close()
        self._pins.clear()
        self.changed.emit()

    def _on_closed(self, pin):
        if pin in self._pins:
            self._pins.remove(pin)
        self.changed.emit()

    def __len__(self):
        return len(self._pins)
