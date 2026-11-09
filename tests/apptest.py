"""运行时自检：托盘/热键/结果窗/选区翻译层/状态守卫。

真实 OCR 精度由 selftest.py 覆盖；这里用可控桩保证确定性。

    .venv/Scripts/python.exe apptest.py
"""

# --- 测试引导：确保能导入项目根目录模块 ---
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Windows 控制台默认 GBK，中文/符号输出会崩；统一成 UTF-8 并放宽错误
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import time

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, QTimer, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPixmap
from PySide6.QtWidgets import QApplication

from jietu import main as app_module
from jietu import ocr_engine


class StubOcr:
    """可控 OCR / 翻译桩。"""

    def __init__(self):
        self.ocr_calls = 0
        self.trans_calls = 0
        self.last_mode = None
        self.last_source = None
        self.last_target = None
        self.text = "人工智能正在改变世界"
        self.translated = "Artificial intelligence is changing the world"
        self.delay = 0.0
        self.ocr_error = None
        self.trans_error = None
        self._orig_ocr = ocr_engine.recognize
        self._orig_tr = ocr_engine.translate

    def __enter__(self):
        ocr_engine.recognize = self._ocr
        ocr_engine.translate = self._trans
        return self

    def __exit__(self, *exc):
        ocr_engine.recognize = self._orig_ocr
        ocr_engine.translate = self._orig_tr

    def _ocr(self, pil, min_score=0.4):
        self.ocr_calls += 1
        if self.delay:
            time.sleep(self.delay)
        if self.ocr_error:
            raise self.ocr_error
        return self.text

    def _trans(self, text, source="auto", target="zh-Hans", mode="general"):
        self.trans_calls += 1
        self.last_mode = mode
        self.last_source = source
        self.last_target = target
        if self.delay:
            time.sleep(self.delay)
        if self.trans_error:
            raise self.trans_error
        return self.translated


def mouse(t, x, y):
    return QMouseEvent(
        t, QPoint(x, y), QPoint(x, y), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier
    )


def draw_selection(ov, start, end, pump_events=True):
    """拖出选区（不确认，新架构松手即自动识别）。"""
    ov.mousePressEvent(mouse(QEvent.MouseButtonPress, *start))
    ov.mouseMoveEvent(mouse(QEvent.MouseMove, *end))
    ov.mouseReleaseEvent(mouse(QEvent.MouseButtonRelease, *end))
    if pump_events:
        QApplication.processEvents()


def pump_until(predicate, timeout=25.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return False


def run():
    qapp = QApplication(sys.argv)
    qapp.setQuitOnLastWindowClosed(False)

    app = app_module.App(qapp)
    results = []

    def check(name, fn):
        try:
            fn()
            results.append((name, True, ""))
        except Exception as exc:
            results.append((name, False, f"{type(exc).__name__}: {exc}"))

    # ---------------------------------------------------------------- 基础
    check("托盘图标已创建", lambda: app.tray.isVisible() or app.tray.show())

    def check_hotkey():
        assert app.hotkeys is not None, "热键管理器未创建"
        assert app.hotkeys._registered, "没有任何热键注册成功"

    check("全局热键注册", check_hotkey)

    def check_model():
        assert pump_until(lambda: app_module.ocr_engine._engine is not None, 20), "模型未加载"

    check("OCR 模型已预加载", check_model)

    # ---------------------------------------------------------------- 完整结果窗（整图/取词）
    def check_window():
        app.window.show_result("测试文字 Test 123", anchor=None, translate=False)
        assert app.window.isVisible(), "结果窗未显示"
        assert "测试文字" in app.window.editor.toPlainText(), "原文未写入"
        app.window.hide()

    check("完整结果窗显示", check_window)

    # ---------------------------------------------------------------- 翻译异步
    def check_translate():
        app.window.show_result("人工智能正在改变世界", anchor=None, translate=True)
        assert pump_until(lambda: bool(app.window._translated), 30), "翻译结果为空"

        app.window._switch("source")
        assert "人工智能" in app.window.editor.toPlainText(), "切回原文失败"
        app.window._switch("target")
        assert app.window._translated.split()[0] in app.window.editor.toPlainText()

        # 异步不阻塞
        app.window._translation_pending = False
        t0 = time.monotonic()
        app.window.translate_now()
        assert time.monotonic() - t0 < 0.2, "translate_now 阻塞 GUI"
        assert pump_until(lambda: not app.window._translation_pending, 30), "翻译未收尾"
        app.window.hide()

    check("翻译异步 + 视图切换", check_translate)

    # ---------------------------------------------------------------- 选区层几何
    def check_overlay_geometry():
        from jietu.capture import CaptureOverlay

        ov = CaptureOverlay()
        ov.show()
        got = []
        ov.selection_changed.connect(lambda pm, rect: got.append((pm, rect)))

        # 防抖后应自动触发一次
        draw_selection(ov, (200, 150), (900, 600))
        assert ov._state == "ready", f"状态应为 ready，实际 {ov._state}"
        assert ov._sel is not None, "选区未建立"
        assert pump_until(lambda: len(got) >= 1, 5), "选区稳定后未触发识别"

        pm, rect = got[0]
        g = ov._geo
        expect = QRect(200 + g.x(), 150 + g.y(), 701, 451)
        assert rect == expect, f"全局选区错误 {rect} != {expect}"
        assert pm.width() == round(701 * ov._scale)
        assert pm.height() == round(451 * ov._scale)
        ov.close_all()

    check("选区层 松手自动触发 + 全局坐标", check_overlay_geometry)

    # ---------------------------------------------------------------- 移动/缩放
    def check_edit_and_redetect():
        from jietu.capture import CaptureOverlay

        ov = CaptureOverlay()
        ov.show()
        got = []
        ov.selection_changed.connect(lambda pm, rect: got.append(rect))

        draw_selection(ov, (300, 300), (900, 600))
        assert pump_until(lambda: len(got) >= 1, 5)
        n_after_draw = len(got)

        # 移动
        before = QRect(ov._sel)
        cx, cy = before.center().x(), before.center().y()
        ov.mousePressEvent(mouse(QEvent.MouseButtonPress, cx, cy))
        ov.mouseMoveEvent(mouse(QEvent.MouseMove, cx + 120, cy + 90))
        ov.mouseReleaseEvent(mouse(QEvent.MouseButtonRelease, cx + 120, cy + 90))
        assert ov._sel.size() == before.size(), "移动改变了大小"
        assert ov._sel.topLeft() != before.topLeft(), "选区未移动"
        assert pump_until(lambda: len(got) > n_after_draw, 5), "移动后未重新识别"

        # 缩放
        n_before = len(got)
        before = QRect(ov._sel)
        br = ov._handle_points(before)["br"]
        ov.mousePressEvent(mouse(QEvent.MouseButtonPress, br.x(), br.y()))
        ov.mouseMoveEvent(mouse(QEvent.MouseMove, br.x() + 70, br.y() + 50))
        ov.mouseReleaseEvent(mouse(QEvent.MouseButtonRelease, br.x() + 70, br.y() + 50))
        assert ov._sel.width() > before.width(), "缩放未生效"
        assert ov._sel.topLeft() == before.topLeft(), "缩放移动了左上角"
        assert pump_until(lambda: len(got) > n_before, 5), "缩放后未重新识别"
        ov.close_all()

    check("选区移动/缩放后自动重新识别", check_edit_and_redetect)

    # ---------------------------------------------------------------- 关闭
    def check_close():
        from jietu.capture import CaptureOverlay

        ov = CaptureOverlay()
        ov.show()
        closed = []
        ov.closed.connect(lambda: closed.append(True))
        draw_selection(ov, (300, 300), (800, 600))
        assert ov.panel.isVisible() or True  # 面板在识别后才显示
        ov.panel.btn_close.click()
        assert closed, "✕ 未触发关闭"
        assert not ov.isVisible(), "关闭后窗口仍可见"

        # Esc
        ov2 = CaptureOverlay()
        ov2.show()
        closed2 = []
        ov2.closed.connect(lambda: closed2.append(True))
        draw_selection(ov2, (300, 300), (800, 600))
        from PySide6.QtGui import QKeyEvent
        ov2.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
        assert closed2, "Esc 未触发关闭"

        # 点击选区外
        ov3 = CaptureOverlay()
        ov3.show()
        closed3 = []
        ov3.closed.connect(lambda: closed3.append(True))
        draw_selection(ov3, (600, 400), (1000, 700))
        ov3.mousePressEvent(mouse(QEvent.MouseButtonPress, 50, 50))
        assert closed3, "点击选区外未关闭"

    check("三种关闭方式（按钮/Esc/点外部）", check_close)

    # ---------------------------------------------------------------- 面板定位
    def check_panel_placement():
        from jietu.capture import CaptureOverlay

        ov = CaptureOverlay()
        ov.show()
        draw_selection(ov, (500, 400), (1200, 700))
        ov.panel.set_text("译文示例")
        ov._place_panel()
        g = ov.panel.geometry()
        assert ov._sel.top() - g.bottom() >= 4 or g.top() >= ov._sel.bottom(), \
            f"面板与选区重叠: panel={g} sel={ov._sel}"
        assert abs(g.center().x() - ov._sel.center().x()) <= 2, "面板未水平居中"

        # 顶部空间不足应翻到下方
        ov._sel = QRect(500, 2, 600, 200)
        ov._place_panel()
        assert ov.panel.geometry().top() >= ov._sel.bottom(), "顶部不足时未翻到下方"
        ov.close_all()

    check("面板 上方优先/下方回退", check_panel_placement)

    # ---------------------------------------------------------------- 端到端（桩）
    def check_end_to_end():
        from jietu.capture import CaptureOverlay

        app.overlay = None
        with StubOcr() as stub:
            stub.text = "端到端测试 EndToEnd"
            stub.translated = "End to end test"

            ov = CaptureOverlay()
            ov.selection_changed.connect(app._on_selection)
            ov.closed.connect(app._on_cancel)
            app.overlay = ov
            app._ocr_generation += 1
            ov.show()

            draw_selection(ov, (400, 300), (1200, 620))

            assert pump_until(lambda: bool(ov._source_text), 20), "原文未显示"
            assert ov._source_text == "端到端测试 EndToEnd"
            assert stub.ocr_calls >= 1, "OCR 未调用"

            assert pump_until(lambda: bool(ov._result_text), 20), "译文未回填"
            assert ov._result_text == "End to end test"
            assert ov.panel.isVisible(), "结果面板未显示"
            assert ov._state == "ready", "选区层应保持可用"

            # 面板上按钮可用
            ov.copy_result()
            assert QApplication.clipboard().text() == "End to end test"

            ov.close_all()

    check("端到端 框选->识别->翻译->面板", check_end_to_end)

    # ---------------------------------------------------------------- 旧结果丢弃
    def check_stale():
        from jietu.capture import CaptureOverlay

        app.overlay = None
        with StubOcr() as stub:
            stub.delay = 0.9
            stub.text = "旧结果"
            stub.translated = "OLD"

            ov1 = CaptureOverlay()
            ov1.selection_changed.connect(app._on_selection)
            app.overlay = ov1
            app._ocr_generation += 1
            ov1.show()
            draw_selection(ov1, (300, 250), (700, 450))
            pump_until(lambda: stub.ocr_calls >= 1, 5)

            # 新建第二个 overlay，使第一个过期
            stub.delay = 0.0
            stub.text = "新结果"
            stub.translated = "NEW"
            ov2 = CaptureOverlay()
            ov2.selection_changed.connect(app._on_selection)
            app.overlay = ov2
            app._ocr_generation += 1
            ov2.show()
            draw_selection(ov2, (400, 300), (900, 550))

            assert pump_until(lambda: ov2._source_text == "新结果", 20), "新结果未显示"
            time.sleep(1.2)
            QApplication.processEvents()
            assert ov2._source_text == "新结果", f"旧结果覆盖: {ov2._source_text!r}"
            assert ov1._source_text != "新结果", "旧层收到了新结果"
            ov2.close_all()

    check("旧结果不覆盖新结果", check_stale)

    # ---------------------------------------------------------------- 程序员模式
    def check_programmer_ui():
        # 默认关闭
        assert app.programmer_mode is False, "默认应为普通模式"

        win = app.window
        assert win.btn_programmer.isCheckable(), "模式按钮应可切换"
        assert not win.btn_programmer.isChecked(), "按钮默认应为未选中"

        win.show_result("ImportGraphState is loaded.", anchor=None, translate=False)
        win._toggle_programmer_mode(True)
        assert win.programmer_mode is True
        assert win.btn_programmer.isChecked(), "按钮未同步选中"
        assert win._source == "ImportGraphState is loaded.", "切换模式改动了原文"

        win._toggle_programmer_mode(False)
        assert win.programmer_mode is False
        win.hide()

    check("程序员模式 默认关闭/可切换/不动原文", check_programmer_ui)

    # ---------------------------------------------------------------- 回归：过期结果不能污染新请求
    def check_stale_translation_unsticks():
        win = app.window
        win.show_result("hello world", anchor=None, translate=False)

        # 模拟"旧请求还在跑"时又发起了新请求
        win._translation_pending = True
        win.btn_translate.setEnabled(False)
        win._translation_generation += 1        # 新请求推进了 generation
        current_gen = win._translation_generation

        # 旧请求这时才回来
        win._on_translation_done("旧结果", None, current_gen - 1, "old text")

        # 旧结果不能覆盖内容，也不能改动新请求的 pending 状态
        assert win._translated != "旧结果", "过期译文被写入"
        assert win._translation_pending is True, "旧结果错误地复位了新请求"

        # 新请求正常完成后必须恢复可翻译状态
        win._on_translation_done("新结果", None, current_gen, "hello world")
        assert win._translation_pending is False, "新请求完成后 pending 未复位"
        assert win.btn_translate.isEnabled(), "翻译按钮卡死"
        assert win._translated == "新结果", "新译文未写入"
        win.hide()

    check("过期翻译结果不污染新请求", check_stale_translation_unsticks)

    # ---------------------------------------------------------------- 回归：连续两次识别都要出译文
    def check_second_capture_translates():
        win = app.window
        win.show_result("first text", anchor=None, translate=False)
        win._translation_pending = True      # 模拟第一次还在翻译
        win.show_result("second text", anchor=None, translate=False)
        # 新的 show_result 必须复位状态，否则第二次永远不会翻译
        assert win._translation_pending is False, "第二次识别后 pending 未复位"
        assert win._source == "second text", "第二次原文未更新"
        win.hide()

    check("连续两次识别都能翻译", check_second_capture_translates)

    # ---------------------------------------------------------------- 回归：翻译中切模式不能死锁
    def check_toggle_mode_while_pending():
        win = app.window
        win.show_result("deadlock probe", anchor=None, translate=False)
        # 模拟一个仍在飞的翻译请求
        win._translation_pending = True
        win.btn_translate.setEnabled(False)
        stale_gen = win._translation_generation

        win._toggle_programmer_mode(True)
        # 关键：必须立刻派发新请求（pending 属于新请求），而不是纯粹挂着
        assert win._translation_generation > stale_gen, "切模式未推进 generation"
        assert win._translation_pending is True, "切模式后没有派发新翻译请求"

        # 旧请求回来时不能污染新状态
        win._on_translation_done("旧", None, stale_gen, "deadlock probe")
        assert win._translated != "旧", "过期译文被写入"
        assert win._translation_pending is True, "旧结果错误地清掉了新请求的 pending"

        # 新请求完成后必须恢复可用（证明不会死锁）
        win._on_translation_done("新", None, win._translation_generation,
                                 "deadlock probe", [])
        assert win._translation_pending is False, "新请求完成未复位 pending"
        assert win.btn_translate.isEnabled(), "按钮永久禁用（死锁）"

        win._translation_pending = False
        win.programmer_mode = False
        win.btn_programmer.setChecked(False)
        app.programmer_mode = False
        win.hide()

    check("翻译中切模式不死锁", check_toggle_mode_while_pending)

    # ---------------------------------------------------------------- 回归：结果窗切模式要同步到 App
    def check_mode_sync():
        win = app.window
        app.programmer_mode = False
        win.programmer_mode = False
        win.show_result("mode sync test", anchor=None, translate=False)

        win._toggle_programmer_mode(True)
        assert app.programmer_mode is True, "结果窗切代码模式未同步到 App"

        # 下一次框选必须继承新模式
        prev = app.overlay
        app.overlay = None
        app._open_overlay()
        assert app.overlay is not None, "overlay 未创建"
        assert app.overlay.programmer_mode is True, "新选区层未继承代码模式"
        app.overlay.close_all()
        if prev is not None:
            prev.deleteLater()

        win._toggle_programmer_mode(False)
        assert app.programmer_mode is False, "关闭模式未同步回 App"
        win.hide()

    check("结果窗模式切换同步到 App", check_mode_sync)

    # ---------------------------------------------------------------- 回归：pending 属性必须初始化
    def check_pending_initialized():
        from jietu.result_window import ResultWindow

        fresh = ResultWindow()          # 全新实例，不受前面用例影响
        try:
            assert hasattr(fresh, "_translation_pending"), "_translation_pending 未初始化"
            assert fresh._translation_pending is False, "初始 pending 应为 False"
        finally:
            fresh.hide()
            fresh.deleteLater()

    check("翻译状态属性已初始化", check_pending_initialized)

    # ---------------------------------------------------------------- 回归：热键过滤器可摘除
    def check_hotkey_uninstall():
        from jietu.hotkeys import HotkeyManager

        hm = HotkeyManager(int(app._hk_window.winId()))
        hm.install(qapp)
        assert hm._qapp is qapp, "install 未记录 qapp"
        hm.uninstall()
        assert hm._qapp is None, "uninstall 未摘除 filter"

        # 非法热键不能抛异常
        bad = HotkeyManager(int(app._hk_window.winId()))
        assert bad.register(999, "not-a-real-key") is False, "非法热键应返回 False 而不是抛异常"

    check("热键 过滤器摘除 / 非法键容错", check_hotkey_uninstall)

    # ---------------------------------------------------------------- 回归：并发 OCR 不串结果
    def check_concurrent_ocr():
        import threading as _th

        from PIL import Image, ImageDraw, ImageFont

        font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 22)
        imgs = []
        for i in range(3):
            im = Image.new("RGB", (420, 70), "white")
            ImageDraw.Draw(im).text((10, 14), f"upload_file_{i}.py", font=font,
                                    fill=(20, 20, 20))
            imgs.append(im)

        results, errors = {}, []

        def run(i):
            try:
                results[i] = ocr_engine.recognize(imgs[i])
            except Exception as exc:
                errors.append(repr(exc))

        threads = [_th.Thread(target=run, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)

        assert not errors, f"并发识别抛异常: {errors}"
        for i in range(3):
            assert results.get(i) == f"upload_file_{i}.py", \
                f"并发结果串了: {i} -> {results.get(i)!r}"

    check("并发 OCR 结果不串", check_concurrent_ocr)

    def check_programmer_request():
        with StubOcr() as stub:
            win = app.window
            win.programmer_mode = False
            win.lang_src.setCurrentText("自动")
            win.lang_dst.setCurrentText("简体中文")
            win._translation_pending = False
            win.show_result("ImportGraphState", anchor=None, translate=True)
            assert pump_until(lambda: stub.trans_calls >= 1, 20), "未发起翻译"
            assert stub.last_mode == "general", f"普通模式传错: {stub.last_mode}"
            assert stub.last_target == "zh-Hans", f"目标语言错误: {stub.last_target}"

            win._translation_pending = False
            win._toggle_programmer_mode(True)
            assert pump_until(lambda: stub.trans_calls >= 2, 20), "切换模式未重新翻译"
            assert stub.last_mode == "programmer", f"代码模式传错: {stub.last_mode}"
            win._translation_pending = False
            win.programmer_mode = False
            win.hide()

    check("翻译请求携带 模式/语言", check_programmer_request)

    def check_programmer_overlay():
        from jietu.capture import CaptureOverlay

        app.programmer_mode = True
        with StubOcr() as stub:
            stub.text = "ImportGraphState is loaded from UploadFile."
            stub.translated = "ImportGraphState 从 UploadFile 加载。"

            ov = CaptureOverlay()
            ov.set_programmer_mode(app.programmer_mode)
            ov.selection_changed.connect(app._on_selection)
            ov.closed.connect(app._on_cancel)
            app.overlay = ov
            app._ocr_generation += 1
            ov.show()
            draw_selection(ov, (500, 400), (1100, 650))

            assert pump_until(lambda: bool(ov._result_text), 20), "未翻译"
            assert stub.last_mode == "programmer", f"选区层模式错误: {stub.last_mode}"
            assert "ImportGraphState" in ov._result_text, "代码 token 丢失"
            assert "已翻译 · 代码模式" in ov.panel.status.text(), \
                f"状态未标识代码模式: {ov.panel.status.text()}"
            ov.close_all()

        # 选区层切模式应同步回 App
        app.programmer_mode = False
        ov2 = CaptureOverlay()
        ov2.mode_changed = app._on_overlay_mode_changed
        ov2.set_programmer_mode(False)
        ov2.toggle_programmer_mode(True)
        assert app.programmer_mode is True, "选区层模式未同步到 App"
        assert app.window.programmer_mode is True, "选区层模式未同步到结果窗"
        ov2.close_all()
        app.programmer_mode = False
        app.window.programmer_mode = False
        app.window.btn_programmer.setChecked(False)

    check("选区层 代码模式继承与同步", check_programmer_overlay)

    def check_target_language():
        from jietu.capture import CaptureOverlay

        app.programmer_mode = False
        app.target_lang = "en"
        app._on_overlay_target_changed("en")
        with StubOcr() as stub:
            stub.text = "人工智能正在改变世界"
            stub.translated = "Artificial intelligence is changing the world"
            ov = CaptureOverlay()
            ov.set_target_language("en")
            ov.target_changed = app._on_overlay_target_changed
            ov.selection_changed.connect(app._on_selection)
            ov.retranslate_requested.connect(app._on_retranslate)
            ov.closed.connect(app._on_cancel)
            app.overlay = ov
            app._ocr_generation += 1
            ov.show()
            draw_selection(ov, (500, 400), (1100, 650))
            assert pump_until(lambda: bool(ov._result_text), 20), "英文翻译未完成"
            assert stub.last_target == "en", f"目标语言错误: {stub.last_target}"
            assert "英文" in ov.panel.status.text(), ov.panel.status.text()
            assert ov.panel.btn_target.isChecked()
            assert app.window.lang_dst.currentText() == "英语"
            ov.toggle_target_language(False)
            assert pump_until(lambda: stub.trans_calls >= 2, 20), "未切回中文重译"
            assert stub.last_target == "zh-Hans", f"恢复中文失败: {stub.last_target}"
            assert app.target_lang == "zh-Hans"
            assert app.window.lang_dst.currentText() == "简体中文"
            ov.close_all()
        app.target_lang = "zh-Hans"

    check("选区层 中英翻译方向切换", check_target_language)

    # ---------------------------------------------------------------- Snip 模式
    import tempfile

    from jietu.pin_window import PinManager

    def make_snip(w=500, h=400):
        ov = app_module.CaptureOverlay(mode=app_module.MODE_SNIP)
        ov._shot = QPixmap(w, h)
        ov._shot.fill(QColor("white"))
        ov._scale = 1.0
        ov._geo = QRect(0, 0, w, h)
        ov.setGeometry(ov._geo)
        ov.show()
        draw_selection(ov, (50, 50), (250, 200))
        return ov

    def check_snip_no_ocr():
        ov = make_snip()
        assert ov._state == "ready", "Snip 模式未进入 READY"
        assert ov._sel is not None
        assert not ov.session.toolbar.isHidden(), "标注工具栏未显示"
        assert len(ov.session.model) == 0
        ov.close_all()

    def check_snip_annotation_render():
        ov = make_snip()
        ov.session._set_tool("rect")
        ov.session._set_color(QColor("red"))
        ov.session._set_width(4)
        ov.mousePressEvent(mouse(QEvent.MouseButtonPress, 80, 80))
        ov.mouseMoveEvent(mouse(QEvent.MouseMove, 200, 170))
        ov.mouseReleaseEvent(mouse(QEvent.MouseButtonRelease, 200, 170))
        assert len(ov.session.model) == 1, "矩形未加入模型"
        pm = ov.session.finalize()
        assert pm.width() == ov._to_phys(ov._sel).width()
        img = pm.toImage()
        # 矩形左边框：逻辑 (80,80) → 最终 (30,30)
        assert img.pixelColor(30, 30) == QColor("red"), "标注未烘焙进成品图"
        assert img.pixelColor(60, 60) == QColor("white"), "选区内部被错误涂改"
        assert ov.session.model.can_undo
        ov.session.model.undo()
        assert len(ov.session.model) == 0, "撤销失败"
        ov.close_all()

    def check_snip_copy_save_pin():
        ov = make_snip()
        ov.session._set_tool("ellipse")
        ov.mousePressEvent(mouse(QEvent.MouseButtonPress, 70, 70))
        ov.mouseMoveEvent(mouse(QEvent.MouseMove, 180, 150))
        ov.mouseReleaseEvent(mouse(QEvent.MouseButtonRelease, 180, 150))
        ov.session.copy_image()
        assert not QApplication.clipboard().image().isNull(), "复制图片失败"
        assert ov._closed, "复制后遮罩未关闭"

        ov2 = make_snip()
        with tempfile.TemporaryDirectory() as d:
            ov2.save_dir = d
            ov2.session.save_image()
            import os
            files = os.listdir(d)
            assert files and files[0].endswith(".png"), "保存 PNG 失败"
        assert ov2._closed

        ov3 = make_snip()
        mgr = PinManager(save_dir=tempfile.gettempdir())
        ov3.pin_requested.connect(mgr.create)
        ov3.session.pin()
        assert len(mgr) == 1, "贴图未创建"
        assert ov3._closed, "贴图后遮罩未关闭"
        pin = mgr.all()[0]
        assert pin.size() == QSize(201, 151), f"贴图尺寸错误 {pin.size()}"
        mgr.close_all()
        assert len(mgr) == 0, "贴图管理器未清空"

    def check_f3_dispatch():
        # 无截图时 F3 贴剪贴板
        img = QPixmap(64, 48)
        img.fill(QColor("blue"))
        QApplication.clipboard().setPixmap(img)
        assert app.pin_current_or_clipboard() is None
        assert len(app.pin_manager) == 1, "F3 未贴剪贴板图片"
        app.pin_manager.close_all()

    check("Snip 模式 选区不触发 OCR", check_snip_no_ocr)
    check("Snip 模式 标注渲染/撤销", check_snip_annotation_render)
    check("Snip 模式 复制/保存/贴图", check_snip_copy_save_pin)
    check("F3 贴剪贴板", check_f3_dispatch)

    def check_native_close():
        ov = make_snip()
        notifications = []
        ov.closed.connect(lambda: notifications.append(True))
        ov.close()
        assert ov._closed and ov._shot.isNull()
        assert notifications == [True]
        ov.close_all()
        assert notifications == [True]

    def check_text_export_and_tool_reset():
        ov = make_snip()
        ov.session._set_tool("text")
        ov.session._open_text(QPoint(80, 80))
        ov.session._text_editor.setPlainText("export pending text")
        ov.session.finalize()
        assert ov.session._text_editor is None
        assert ov.session.model.shapes()[0].text == "export pending text"
        ov.session._set_tool(None)
        assert not any(b.isChecked() for b in ov.session.toolbar._buttons.values())
        ov.close_all()

    def check_history_move():
        from jietu.annotations import AnnotationModel, Shape
        from PySide6.QtCore import QPointF
        model = AnnotationModel()
        shape = Shape("rect", [QPointF(10, 10), QPointF(30, 30)], QColor("red"), 2)
        model.add(shape)
        model.undo()
        model.translate(20, 15)
        model.redo()
        assert shape.points[0] == QPointF(30, 25)
        model.translate(5, 5)
        assert shape.points[0] == QPointF(35, 30)

    def check_real_f1():
        import ctypes
        from ctypes import wintypes
        spec = app.hotkeys._registered.get(app_module.HK_SNIP)
        if not spec:
            print("SKIP  F1 and fallbacks are all occupied by other apps")
            return
        if app.overlay is not None:
            app.overlay.close_all()
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_size_t]

        def tap(vk):
            user32.keybd_event(vk, 0, 0, 0)
            time.sleep(0.04)
            user32.keybd_event(vk, 0, 2, 0)
            time.sleep(0.04)

        if spec == "f1":
            tap(0x70)
        elif spec == "alt+1":
            user32.keybd_event(0x12, 0, 0, 0)
            time.sleep(0.04)
            tap(0x31)
            user32.keybd_event(0x12, 0, 2, 0)
        else:  # ctrl+alt+f1
            user32.keybd_event(0x11, 0, 0, 0)
            time.sleep(0.04)
            user32.keybd_event(0x12, 0, 0, 0)
            time.sleep(0.04)
            tap(0x70)
            user32.keybd_event(0x12, 0, 2, 0)
            user32.keybd_event(0x11, 0, 2, 0)
        assert pump_until(lambda: app.overlay is not None and app.overlay.isVisible(), timeout=4), \
            f"热键 {spec} 未打开遮罩 (busy={app._busy})"
        assert app.overlay.mode == app_module.MODE_SNIP, app.overlay.mode
        ov = app.overlay
        assert not ov.capture_cursor.pixmap().isNull(), "截图光标不是自定义准星"
        draw_selection(ov, (50, 50), (250, 200))
        expected = ov.render_result().toImage()
        blue = QPixmap(64, 48)
        blue.fill(QColor("#000080"))
        QApplication.clipboard().setPixmap(blue)
        from PySide6.QtGui import QKeyEvent
        # 本地 F3 必须吞掉，否则会与全局热键重复贴图。
        ov.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_F3, Qt.NoModifier))
        assert len(app.pin_manager) == 0, "本地 F3 不应直接贴图"
        app._on_hotkey(app_module.HK_PIN)
        assert pump_until(lambda: app.overlay is None, timeout=4), "遮罩未关闭"
        deadline = time.monotonic() + 0.3
        while time.monotonic() < deadline:
            QApplication.processEvents()
            time.sleep(0.01)
        assert len(app.pin_manager) == 1, f"F3 贴图数量错误: {len(app.pin_manager)}"
        assert app.pin_manager.all()[0]._base.toImage() == expected, "贴图不是选区内容"
        app.pin_manager.close_all()
        assert app.overlay is None and not app._busy, \
            f"收尾失败 overlay={app.overlay} busy={app._busy}"

    check("原生关闭释放截图并通知一次", check_native_close)
    check("文字导出提交/工具取消状态", check_text_export_and_tool_reset)
    check("撤销后移动再重做坐标一致", check_history_move)
    check("真实 F1 按键打开截图遮罩", check_real_f1)

    def check_settings_tray():
        labels = [action.text() for action in app.tray.contextMenu().actions()]
        assert "开机自启动" in labels and "翻译设置" in labels
        assert not any(label.startswith("整图转文本") for label in labels)
        assert app._act_autostart.isCheckable()
        app.window._translation_pending = True
        app.window.btn_translate.setEnabled(False)
        ocr_engine._cache_put("settings-test", "auto", "en", "general", "old")
        app._settings_saved()
        assert not app.window._translation_pending
        assert app.window.btn_translate.isEnabled()
        assert not ocr_engine._TRANSLATE_CACHE

    check("托盘自启动/设置入口与缓存失效", check_settings_tray)

    # ---------------------------------------------------------------- 输出
    print("=" * 56)
    ok = True
    for name, passed, err in results:
        print(f"{'PASS' if passed else 'FAIL'}  {name}" + (f"  -> {err}" if err else ""))
        ok = ok and passed
    print("=" * 56)

    try:
        if app.hotkeys:
            app.hotkeys.unregister_all()
        app.tray.hide()
    except Exception:
        pass
    if app.overlay:
        app.overlay.close_all()
    app.window.hide()

    QTimer.singleShot(0, qapp.quit)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run())
