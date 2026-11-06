"""Deterministic native export checks; run directly with the project Python."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, QRect, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap, QTransform
from PySide6.QtWidgets import QApplication

from jietu import capture, pin_window
from jietu.annotations import Shape, _effect_image

APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


def checker(width, height):
    img = QImage(width, height, QImage.Format_RGB32)
    for y in range(height):
        for x in range(width):
            img.setPixelColor(x, y, QColor("white" if (x + y) % 2 else "black"))
    return QPixmap.fromImage(img)


def pixels(image):
    if isinstance(image, QPixmap):
        image = image.toImage()
    image = image.convertToFormat(QImage.Format_RGBA8888)
    return image.width(), image.height(), bytes(image.constBits())


class Screen:
    def __init__(self, rect, pixmap, dpr):
        self.rect, self.pixmap, self.dpr = rect, pixmap, dpr
        self.calls = 0

    def geometry(self):
        return QRect(self.rect)

    def devicePixelRatio(self):
        return self.dpr

    def grabWindow(self, *args):
        self.calls += 1
        return QPixmap(self.pixmap)


def overlay(screens):
    class Desktop:
        @staticmethod
        def screens():
            return screens
    with patch.object(capture, "QGuiApplication", Desktop):
        return capture.CaptureOverlay(capture.MODE_SNIP)


class LosslessTests(unittest.TestCase):
    def setUp(self):
        self.windows = []

    def tearDown(self):
        for window in self.windows:
            window.close()

    def make(self, screens):
        ov = overlay(screens)
        self.windows.append(ov)
        return ov

    def test_checkerboard_native_crop_png_and_one_capture(self):
        native = checker(200, 140)
        screen = Screen(QRect(0, 0, 100, 70), native, 2)
        ov = self.make([screen])
        ov._sel = QRect(7, 9, 41, 31)
        result = ov.render_result()
        expected = native.copy(14, 18, 82, 62)
        self.assertEqual(pixels(result), pixels(expected))
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "native.png")
            self.assertTrue(result.save(path, "PNG"))
            self.assertEqual(pixels(QImage(path)), pixels(expected))
        ov.render_result()
        self.assertEqual(screen.calls, 1)
        self.assertEqual(ov.export_size(ov._sel), expected.size())

    def test_fractional_dpi_actual_xy_ratios_negative_origin(self):
        # Rounded capture dimensions deliberately differ from the advertised DPR.
        native = checker(127, 99)
        left = Screen(QRect(-101, -17, 101, 79), native, 1.25)
        right = Screen(QRect(0, 0, 100, 79), checker(200, 158), 2)
        ov = self.make([left, right])
        ov._sel = QRect(7, 9, 43, 31)
        result = ov.export_selection(ov._sel)
        sx, sy = 127 / 101, 99 / 79
        bounds = QRect(round(7 * sx), round(9 * sy),
                       round(50 * sx) - round(7 * sx),
                       round(40 * sy) - round(9 * sy))
        self.assertEqual(pixels(result.crop), pixels(native.copy(bounds)))
        self.assertEqual(result.scale_x, sx)
        self.assertEqual(result.scale_y, sy)
        mapped = result.transform.map(QPointF(7, 9))
        self.assertAlmostEqual(mapped.x(), 7 * sx - bounds.x())
        self.assertAlmostEqual(mapped.y(), 9 * sy - bounds.y())
        self.assertEqual((left.calls, right.calls), (1, 1))
        # Right monitor starts at a nonzero overlay-local x/y offset.
        ov._sel = QRect(108, 26, 43, 31)
        right_export = ov.export_selection(ov._sel)
        self.assertEqual(right_export.origin, QPointF(101, 17))
        self.assertEqual(pixels(right_export.crop),
                         pixels(right.pixmap.copy(14, 18, 86, 62)))
        self.assertEqual(right_export.transform.map(QPointF(108, 26)), QPointF())

    def test_cross_monitor_nearest_neighbour(self):
        left = Screen(QRect(-40, 0, 40, 40), checker(50, 50), 1.25)
        right = Screen(QRect(0, 0, 40, 40), checker(80, 80), 2)
        ov = self.make([left, right])
        ov._sel = QRect(0, 0, 80, 40)
        export = ov.export_selection(ov._sel)
        img = export.crop.toImage()
        for y in range(img.height()):
            for x in range(img.width()):
                self.assertIn(img.pixelColor(x, y).red(), (0, 255))
        self.assertEqual(img.size(), QSize(160, 80))
        self.assertEqual(pixels(export.crop.copy(0, 0, 80, 80)),
                         pixels(left.pixmap.scaled(80, 80, Qt.IgnoreAspectRatio,
                                                   Qt.FastTransformation)))
        self.assertEqual((left.calls, right.calls), (1, 1))

    def test_synthetic_shot_fallback_and_ocr_unchanged(self):
        ov = self.make([Screen(QRect(0, 0, 100, 80), checker(200, 160), 2)])
        ov._shot = checker(150, 120)
        ov._scale = 1.5
        ov._sel = QRect(7, 9, 41, 31)
        self.assertEqual(pixels(ov.render_result()), pixels(ov._crop(ov._sel)))
        self.assertEqual(pixels(ov.export_selection(ov._sel).source), pixels(ov._shot))
        ov.mode = capture.MODE_TRANSLATE
        received = []
        ov.selection_changed.connect(lambda pm, rect: received.append((pm, rect)))
        ov._emit_selection()
        self.assertEqual(pixels(received[0][0]), pixels(ov._crop(ov._sel)))

    def test_annotations_keep_untouched_native_pixels_and_offsets(self):
        native = checker(127, 99)
        ov = self.make([Screen(QRect(-101, -17, 101, 79), native, 1.25)])
        ov._sel = QRect(7, 9, 70, 50)
        base = ov.render_result()
        shape = Shape("line", [QPointF(20, 22), QPointF(35, 22)], QColor("red"), 4)
        ov.session.model.add(shape)
        output = ov.render_result().toImage()
        original = base.toImage()
        transform = ov.export_selection(ov._sel).transform
        center = transform.map(QPointF(27, 22)).toPoint()
        self.assertEqual(output.pixelColor(center), QColor("red"))
        changed = 0
        for y in range(output.height()):
            for x in range(output.width()):
                if output.pixel(x, y) != original.pixel(x, y):
                    changed += 1
                    self.assertLess(abs(y - center.y()), 5)
        self.assertGreater(changed, 10)
        self.assertEqual(pixels(output.copy(0, output.height() - 10, output.width(), 10)),
                         pixels(original.copy(0, original.height() - 10, original.width(), 10)))

    def test_effect_cache_tracks_source_origin_xy_scale(self):
        shape = Shape("mosaic", [QPointF(5, 5), QPointF(15, 15)], QColor("red"), 4)
        red = QImage(60, 60, QImage.Format_RGB32)
        red.fill(QColor("red"))
        blue = QImage(red.size(), red.format())
        blue.fill(QColor("blue"))
        _effect_image(shape, red, QPointF(), 1.25)
        first_key = shape._cache_key
        output = _effect_image(shape, blue, QPointF(), (1.25, 1.5))
        self.assertNotEqual(shape._cache_key, first_key)
        self.assertEqual(output.pixelColor(0, 0), QColor("blue"))
        key = shape._cache_key
        _effect_image(shape, blue, QPointF(1, 1), (1.25, 1.5))
        self.assertNotEqual(key, shape._cache_key)

    def test_final_effect_does_not_reuse_preview(self):
        ov = self.make([Screen(QRect(0, 0, 80, 60), checker(100, 75), 1.25),
                        Screen(QRect(80, 0, 80, 60), checker(160, 120), 2)])
        ov._sel = QRect(5, 5, 60, 45)
        shape = Shape("mosaic", [QPointF(15, 15), QPointF(30, 30)], QColor("red"), 5)
        ov.session.model.add(shape)
        _effect_image(shape, ov._shot.toImage(), QPointF(), ov._scale)
        preview_key = shape._cache_key
        output = ov.render_result()
        self.assertNotEqual(shape._cache_key, preview_key)
        export = ov.export_selection(ov._sel)
        reference = export.crop
        shape._cache = None
        from jietu.annotations import draw_shapes
        painter = QPainter(reference)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setTransform(export.transform)
        painter.setClipRect(ov._sel)
        draw_shapes(painter, [shape], export.source.toImage(), export.origin,
                    (export.scale_x, export.scale_y))
        painter.end()
        self.assertEqual(pixels(output), pixels(reference))

    def test_pin_zoom_opacity_rotation_flip_export(self):
        native = checker(51, 37)
        # Add an asymmetric marker to distinguish all rotations/flips.
        painter = QPainter(native)
        painter.fillRect(QRect(0, 0, 9, 7), QColor("red"))
        painter.end()
        with tempfile.TemporaryDirectory() as directory:
            pin = pin_window.PinWindow(native, QSize(41, 30), QPoint(), directory)
            self.windows.append(pin)
            pin._zoom = 2.7
            pin._opacity = 0.4
            pin._resize_display()
            for rot in (0, 90, 180, 270):
                for flip in (False, True):
                    pin._rot, pin._flip_h = rot, flip
                    pin._rebuild()
                    expected = native.toImage().mirrored(flip, False)
                    expected = expected.transformed(QTransform().rotate(rot))
                    path = pin.save_quick()
                    self.assertIsNotNone(path)
                    self.assertEqual(pixels(QImage(str(path))), pixels(expected))
                    pin.copy_image()
                    self.assertEqual(pixels(APP.clipboard().image()), pixels(expected))

    def test_pin_save_errors_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            pin = pin_window.PinWindow(checker(20, 20), QSize(20, 20), QPoint(), directory)
            self.windows.append(pin)
            with patch.object(pin_window, "save_pixmap", side_effect=OSError("write failed")), \
                 patch.object(pin_window.QMessageBox, "warning") as warning, \
                 patch.object(pin_window.QFileDialog, "getSaveFileName", return_value=(str(Path(directory) / "out.png"), "")):
                pin.save_as()
                self.assertIsNone(pin.save_quick())
                self.assertEqual(warning.call_count, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
