"""Snipaste 模式会话：标注、取色、窗口识别、复制/保存/贴图。

覆盖层只负责框选与画桌面，具体交互全部委托到这里，
翻译模式的旧代码路径保持原样。
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QMessageBox, QPlainTextEdit

from .annotations import AnnotationModel, Shape, draw_shape, draw_shapes, shape_rect
from .magnifier import paint_magnifier
from .paths import default_save_dir, save_pixmap, unique_png_path
from .toolbar import AnnoToolbar, place_near_selection
from .window_detect import window_rect_at


class _TextEditor(QPlainTextEdit):
    def __init__(self, parent, on_commit, on_cancel, color: QColor, font_size: int):
        super().__init__(parent)
        self._commit = on_commit
        self._cancel = on_cancel
        self._done = False
        self.setMinimumWidth(80)
        self.setFixedHeight(max(38, font_size * 3))
        self.setStyleSheet(
            f"QPlainTextEdit {{ background: rgba(20,22,26,190); color: {color.name()};"
            f" border: 1px dashed #8a9099; padding: 2px; font-size: {font_size}px; }}"
        )
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and not (
            e.modifiers() & Qt.ShiftModifier
        ):
            self._finish(True)
            return
        if e.key() == Qt.Key_Escape:
            self._finish(False)
            return
        super().keyPressEvent(e)

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        if e.reason() not in (Qt.PopupFocusReason, Qt.ActiveWindowFocusReason):
            self._finish(True, restore_focus=False)

    def _finish(self, commit: bool, restore_focus: bool = True):
        if self._done:
            return
        self._done = True
        text = self.toPlainText()
        self.hide()
        if commit and text.strip():
            self._commit(text, restore_focus)
        else:
            self._cancel(restore_focus)
        self.deleteLater()


class SnipSession:
    def __init__(self, overlay):
        self.overlay = overlay
        self.tool: str | None = None
        self.color = QColor("#e8503a")
        self.width = 3
        self.font_size = 16

        self.model = AnnotationModel(overlay)
        self.model.changed.connect(self._on_model_changed)

        self._src_image = None
        self._pending: Shape | None = None
        self._drawing = False
        self._last = QPointF()
        self._picker = False
        self._detect = False
        self._detect_rect: QRect | None = None
        self._hover: QPoint | None = None
        self._text_editor: _TextEditor | None = None
        self._text_anchor = QPoint()
        self._toast = ""
        self._toast_timer = QTimer(overlay)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self._clear_toast)

        self.toolbar = AnnoToolbar(overlay)
        self.toolbar.hide()
        self.toolbar.tool_changed.connect(self._on_tool_changed)
        self.toolbar.undo_clicked.connect(self._undo)
        self.toolbar.redo_clicked.connect(self._redo)
        self.toolbar.color_changed.connect(self._set_color)
        self.toolbar.width_changed.connect(self._set_width)
        self.toolbar.copy_clicked.connect(self.copy_image)
        self.toolbar.save_clicked.connect(self.save_image)
        self.toolbar.pin_clicked.connect(self.pin)
        self.toolbar.close_clicked.connect(overlay.close_all)
        self._sync_buttons()

    # -------------------------------------------------- 状态
    def has_shapes(self) -> bool:
        return len(self.model) > 0

    def _source_image(self):
        ov = self.overlay
        if ov._shot is None or ov._shot.isNull():
            return None
        if (self._src_image is None
                or getattr(self, "_src_key", None) != ov._shot.cacheKey()):
            self._src_image = ov._shot.toImage()
            self._src_key = ov._shot.cacheKey()
        return self._src_image

    def _phys_point(self, pos: QPoint) -> QPoint:
        s = self.overlay._scale
        return QPoint(int(round(pos.x() * s)), int(round(pos.y() * s)))

    def _sync_buttons(self):
        self.toolbar.set_undo_enabled(self.model.can_undo)
        self.toolbar.set_redo_enabled(self.model.can_redo)

    def _on_model_changed(self):
        self._sync_buttons()
        self.overlay.update()

    def _set_tool(self, tool: str | None):
        self.tool = tool
        self.toolbar.set_active_tool(tool)
        self.overlay.setCursor(self.overlay.capture_cursor if tool else Qt.SizeAllCursor)
        self.overlay.update()

    def _on_tool_changed(self, tool):
        self.tool = tool
        if tool:
            self._picker = False
            self._detect = False
            self._detect_rect = None
        self.overlay.setCursor(self.overlay.capture_cursor if tool else Qt.SizeAllCursor)
        self.overlay.update()

    def _set_color(self, color: QColor):
        self.color = QColor(color)

    def _set_width(self, width: int):
        self.width = width

    def _undo(self):
        self.model.undo()
        self._sync_buttons()

    def _redo(self):
        self.model.redo()
        self._sync_buttons()

    def _clear_toast(self):
        self._toast = ""
        self.overlay.update()

    def _show_toast(self, text: str):
        self._toast = text
        self._toast_timer.start(1400)
        self.overlay.update()

    # -------------------------------------------------- 选区生命周期
    def after_selection(self):
        if self.overlay._sel is None:
            return
        self.toolbar.show()
        self.place_toolbar()
        self.overlay.setFocus()
        self.overlay.update()

    def place_toolbar(self):
        if not self.toolbar.isVisible():
            return
        sel = self.overlay._sel
        if sel is None:
            self.toolbar.hide()
            return
        place_near_selection(
            self.toolbar, sel, 8,
            QSize(self.overlay.width(), self.overlay.height()),
        )

    def on_selection_changed(self):
        self.place_toolbar()
        self.overlay.update()

    def on_selection_cleared(self):
        self.toolbar.hide()
        self._pending = None
        self._drawing = False
        self.overlay.update()

    # -------------------------------------------------- 鼠标
    def handle_press(self, e, pos: QPoint) -> bool:
        ov = self.overlay
        sel = ov._sel

        if e.button() == Qt.RightButton:
            if self._text_editor is not None:
                self._text_editor._finish(False)
                return True
            if self._picker or self._detect or self.tool:
                self._picker = False
                self._detect = False
                self._detect_rect = None
                self._pending = None
                self._drawing = False
                self._set_tool(None)
                ov.update()
                return True
            ov.close_all()
            return True

        if e.button() != Qt.LeftButton:
            return False

        if self._picker:
            self._copy_color(pos)
            return True

        if self._detect:
            if self._detect_rect is None:
                gp = ov._geo.topLeft() + pos
                self._detect_rect = window_rect_at(gp, ov._geo, ov._scale)
            if self._detect_rect is not None:
                self._adopt_detection()
            return True

        if sel is None:
            return False

        if self.tool is not None:
            if not sel.contains(pos):
                return True
            if self.tool == "text":
                self._open_text(pos)
                return True
            if self.tool == "eraser":
                self.model.remove_at(QPointF(pos), tol=4.0)
                return True
            self._drawing = True
            self._pending = Shape(
                kind=self.tool,
                points=[QPointF(pos), QPointF(pos)],
                color=QColor(self.color),
                width=float(self.width),
            )
            self._last = QPointF(pos)
            ov.update()
            return True

        # 没有工具时允许移动选区；已有标注则禁用缩放手柄
        if self.has_shapes() and ov._hit_handle(pos):
            return True
        return False

    def handle_move(self, e, pos: QPoint) -> bool:
        ov = self.overlay

        if self._drawing and self._pending is not None:
            if self._pending.kind in ("pen", "highlighter"):
                if (QPointF(pos) - self._last).manhattanLength() >= 1.5:
                    self._pending.points.append(QPointF(pos))
                    self._last = QPointF(pos)
            else:
                self._pending.points[1] = QPointF(pos)
            ov.update()
            return True

        if self.tool == "eraser" and (e.buttons() & Qt.LeftButton):
            if self.model.remove_at(QPointF(pos), tol=4.0):
                ov.update()
            return True

        if self.tool is not None:
            ov.setCursor(ov.capture_cursor)
            return True

        if self._picker:
            self._hover = pos
            ov.update()
            return True

        if self._detect:
            self._hover = pos
            gp = ov._geo.topLeft() + pos
            self._detect_rect = window_rect_at(gp, ov._geo, ov._scale)
            ov.update()
            return True

        if self.has_shapes() and not ov._drag_mode and ov._hit_handle(pos):
            ov.setCursor(Qt.ArrowCursor)
            return True

        return False

    def handle_release(self, e, pos: QPoint) -> bool:
        if self._drawing:
            self._drawing = False
            sh = self._pending
            self._pending = None
            if sh is not None and self._valid(sh):
                self.model.add(sh)
            self.overlay.update()
            return True
        if self.tool is not None or self._picker or self._detect:
            return True
        return False

    def handle_double_click(self, e, pos: QPoint) -> bool:
        if e.button() != Qt.LeftButton:
            return False
        if self.tool is not None or self._picker or self._detect:
            return True
        if self.overlay._sel is not None:
            self.copy_image()
            return True
        return False

    # -------------------------------------------------- 键盘
    def handle_key(self, e) -> bool:
        ov = self.overlay
        key = e.key()
        mods = e.modifiers()
        ctrl = bool(mods & Qt.ControlModifier)

        if self._text_editor is not None:
            return False

        if key == Qt.Key_Escape:
            if self._picker or self._detect or self.tool:
                self._picker = False
                self._detect = False
                self._detect_rect = None
                self._pending = None
                self._drawing = False
                self._set_tool(None)
                ov.update()
                return True
            return False

        if key == Qt.Key_Tab:
            self._detect = not self._detect
            self._detect_rect = None
            if self._detect:
                self._picker = False
                self._set_tool(None)
            ov.setCursor(Qt.ArrowCursor if self._detect else ov.capture_cursor)
            ov.update()
            return True

        if key == Qt.Key_C and not ctrl:
            self._picker = not self._picker
            if self._picker:
                self._detect = False
                self._detect_rect = None
                self._set_tool(None)
            ov.update()
            return True

        if ctrl and key == Qt.Key_C:
            self.copy_image()
            return True
        if ctrl and key == Qt.Key_S:
            self.save_image()
            return True
        if ctrl and key == Qt.Key_Z:
            self._undo()
            return True
        if ctrl and key == Qt.Key_Y:
            self._redo()
            return True

        if key in (Qt.Key_Return, Qt.Key_Enter):
            if self.tool is not None:
                return True
            if ov._sel is not None:
                self.copy_image()
                return True
            return False

        if key == Qt.Key_F3:
            # F3 统一由 RegisterHotKey 分发，避免关闭遮罩后再贴一次剪贴板。
            return True

        if key in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down) and ov._sel is not None:
            step = 10 if (mods & Qt.ShiftModifier) else 1
            dx = -step if key == Qt.Key_Left else step if key == Qt.Key_Right else 0
            dy = -step if key == Qt.Key_Up else step if key == Qt.Key_Down else 0
            old = QRect(ov._sel)
            new = old.translated(dx, dy)
            new.moveLeft(max(0, min(new.left(), ov.width() - new.width())))
            new.moveTop(max(0, min(new.top(), ov.height() - new.height())))
            delta = new.topLeft() - old.topLeft()
            ov._sel = new
            self.model.translate(delta.x(), delta.y())
            self.place_toolbar()
            ov.update()
            return True

        return False

    # -------------------------------------------------- 文本
    def _open_text(self, pos: QPoint):
        if self._text_editor is not None:
            return
        self._text_anchor = QPoint(pos)
        ed = _TextEditor(self.overlay, self._commit_text, self._cancel_text,
                         self.color, self.font_size)
        self._text_editor = ed
        x = min(pos.x(), max(4, self.overlay.width() - 120))
        y = min(pos.y(), max(4, self.overlay.height() - ed.height() - 4))
        ed.move(x, y)
        ed.resize(min(260, max(80, self.overlay.width() - x - 4)), ed.height())
        ed.show()
        ed.setFocus()

    def _commit_text(self, text: str, restore_focus: bool = True):
        self._text_editor = None
        sh = Shape(
            kind="text",
            points=[QPointF(self._text_anchor)],
            color=QColor(self.color),
            width=float(self.width),
            text=text,
            font_size=float(self.font_size),
        )
        self.model.add(sh)
        if restore_focus:
            self.overlay.setFocus()
        self.overlay.update()

    def _cancel_text(self, restore_focus: bool = True):
        self._text_editor = None
        if restore_focus:
            self.overlay.setFocus()
        self.overlay.update()

    # -------------------------------------------------- 取色 / 窗口
    def _copy_color(self, pos: QPoint):
        from .magnifier import sample_color

        img = self._source_image()
        if img is None:
            return
        color = sample_color(img, self._phys_point(pos))
        QGuiApplication.clipboard().setText(color.name().upper())
        self._picker = False
        self._show_toast(f"已复制 {color.name().upper()}")

    def _adopt_detection(self):
        rect = QRect(self._detect_rect)
        if rect.width() < 4 or rect.height() < 4:
            return
        self._detect = False
        self._detect_rect = None
        self.overlay.set_selection(rect)
        self.after_selection()

    def _valid(self, sh: Shape) -> bool:
        if sh.kind in ("pen", "highlighter"):
            return len(sh.points) >= 2
        if sh.kind in ("rect", "ellipse", "mosaic", "blur"):
            if len(sh.points) < 2:
                return False
            r = QRectF(sh.points[0], sh.points[1]).normalized()
            return r.width() >= 2 or r.height() >= 2
        return len(sh.points) >= 2

    # -------------------------------------------------- 绘制
    def paint(self, p: QPainter):
        ov = self.overlay
        sel = ov._sel

        if self._detect_rect is not None:
            p.save()
            p.setPen(QPen(QColor(76, 217, 100), 2))
            p.setBrush(QColor(76, 217, 100, 36))
            p.drawRect(self._detect_rect)
            p.restore()

        if sel is not None:
            p.save()
            p.setClipRect(sel)
            src = self._source_image()
            draw_shapes(p, self.model.shapes(), src, QPointF(0, 0), ov._scale)
            if self._pending is not None:
                if self._pending.kind == "blur" and self._drawing:
                    p.setPen(QPen(QColor(90, 170, 255), 1, Qt.DashLine))
                    p.setBrush(Qt.NoBrush)
                    p.drawRect(shape_rect(self._pending))
                else:
                    draw_shape(p, self._pending, src, QPointF(0, 0), ov._scale)
            p.restore()

        if self._picker and self._hover is not None:
            img = self._source_image()
            if img is not None:
                gp = ov._geo.topLeft() + self._hover
                paint_magnifier(
                    p, img, self._phys_point(self._hover), ov._scale,
                    self._hover, QSize(ov.width(), ov.height()), gp,
                )

        if self._toast:
            p.save()
            m = p.fontMetrics()
            tw = m.horizontalAdvance(self._toast) + 24
            th = m.height() + 10
            x = (ov.width() - tw) // 2
            y = 16
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(24, 26, 30, 225))
            p.drawRoundedRect(QRect(x, y, tw, th), 5, 5)
            p.setPen(QColor(230, 233, 238))
            p.drawText(QRect(x, y, tw, th), Qt.AlignCenter, self._toast)
            p.restore()

    # -------------------------------------------------- 输出
    def finalize(self) -> QPixmap:
        if self._text_editor is not None:
            self._text_editor._finish(True)
        ov = self.overlay
        sel = ov._sel
        if sel is None:
            return QPixmap()
        export = ov.export_selection(sel)
        crop = export.crop
        shapes = self.model.shapes()
        if not shapes or crop.isNull():
            return crop
        src = export.source.toImage()
        p = QPainter(crop)
        try:
            p.setRenderHint(QPainter.Antialiasing)
            p.setRenderHint(QPainter.SmoothPixmapTransform, False)
            p.setTransform(export.transform)
            p.setClipRect(QRectF(sel))
            draw_shapes(p, shapes, src, export.origin,
                        (export.scale_x, export.scale_y))
        finally:
            p.end()
        return crop

    def copy_image(self):
        pm = self.finalize()
        if pm.isNull():
            return
        QGuiApplication.clipboard().setPixmap(pm)
        self.overlay.close_all()

    def save_image(self):
        pm = self.finalize()
        if pm.isNull():
            return
        directory = self.overlay.save_dir or default_save_dir()
        try:
            path = save_pixmap(pm, unique_png_path(directory))
        except Exception as exc:
            QMessageBox.warning(self.overlay, "保存失败", str(exc))
            return
        self.overlay.close_all()
        print(f"[save] {path}")

    def pin(self):
        ov = self.overlay
        sel = ov._sel
        if sel is None:
            return
        pm = self.finalize()
        if pm.isNull():
            return
        logical = QSize(max(1, sel.width()), max(1, sel.height()))
        global_pos = ov._geo.topLeft() + sel.topLeft()
        ov.pin_requested.emit(pm, logical, global_pos)
        ov.close_all()

    def cleanup(self):
        if self._text_editor is not None:
            self._text_editor._done = True
            self._text_editor.hide()
            self._text_editor.deleteLater()
            self._text_editor = None
        self.toolbar.hide()
        self._pending = None
        self._drawing = False
        self._src_image = None
