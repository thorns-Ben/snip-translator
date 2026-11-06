"""Native settings form. Opening/cancelling never writes or contacts the network."""

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QVBoxLayout,
)

from . import settings


def test_connection(config: settings.TranslationSettings) -> bool:
    """Test only the supplied draft; no load, save, translation text or raw errors."""
    try:
        settings.validate_settings(config)
        if not config.enabled or not config.api_key:
            return False
        from .llm_translate import _http_post

        data = _http_post(config.api_url, {
            "model": config.model,
            "messages": [{"role": "user", "content": "Reply OK"}],
            "max_tokens": 8,
            "stream": False,
        }, config.api_key, 8)
        return bool(data.get("choices", [{}])[0].get("message", {}).get("content"))
    except Exception:
        return False


class _TestSignals(QObject):
    finished = Signal(bool)


class _TestWorker(QRunnable):
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.signals = _TestSignals()

    def run(self):
        self.signals.finished.emit(test_connection(self.config))


class SettingsDialog(QDialog):
    # No credentials in signals. Main connects this to cache invalidation.
    saved = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("翻译设置")
        self.setMinimumWidth(540)
        self._worker = None
        notice = ""
        try:
            config = settings.load_settings()
        except settings.SettingsError as exc:
            config = settings.TranslationSettings(enabled=False)
            notice = str(exc)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        self.enabled_check = QCheckBox("启用 LLM 翻译")
        self.enabled_check.setChecked(config.enabled)
        layout.addWidget(self.enabled_check)
        form = QFormLayout()
        form.setSpacing(12)
        self.api_url_edit = QLineEdit(config.api_url)
        self.model_edit = QLineEdit(config.model)
        self.api_key_edit = QLineEdit(config.api_key)
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.show_key_check = QCheckBox("显示")
        self.show_key_check.toggled.connect(self._show_key)
        key_row = QHBoxLayout()
        key_row.addWidget(self.api_key_edit)
        key_row.addWidget(self.show_key_check)
        form.addRow("完整 HTTPS API 地址", self.api_url_edit)
        form.addRow("模型", self.model_edit)
        form.addRow("API Key", key_row)
        layout.addLayout(form)
        explanation = QLabel("API Key 使用当前 Windows 用户加密保存。留空可清除已保存的 Key。\n"
                             "取消不会保存。关闭 LLM 后将使用现有的免费翻译回退。")
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        self.test_button = QPushButton("测试连接（将发送网络请求）")
        self.test_button.clicked.connect(self._start_test)
        layout.addWidget(self.test_button)
        self.status_label = QLabel(notice)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def showEvent(self, event):
        # Main reuses this instance: discard cancelled edits on every reopening.
        try:
            config = settings.load_settings()
            notice = ""
        except settings.SettingsError as exc:
            config = settings.TranslationSettings(enabled=False)
            notice = str(exc)
        self.enabled_check.setChecked(config.enabled)
        self.api_url_edit.setText(config.api_url)
        self.model_edit.setText(config.model)
        self.api_key_edit.setText(config.api_key)
        self.show_key_check.setChecked(False)
        self.status_label.setText(notice)
        super().showEvent(event)

    @Slot(bool)
    def _show_key(self, visible):
        self.api_key_edit.setEchoMode(
            QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password)

    def draft_settings(self):
        return settings.TranslationSettings(
            enabled=self.enabled_check.isChecked(),
            api_url=self.api_url_edit.text().strip(),
            model=self.model_edit.text().strip(),
            api_key=self.api_key_edit.text().strip(),
        )

    @Slot()
    def accept(self):
        try:
            settings.save_settings(self.draft_settings())
        except settings.SettingsError as exc:
            self.status_label.setText(str(exc))
            return
        self.saved.emit()
        super().accept()

    @Slot()
    def _start_test(self):
        config = self.draft_settings()
        try:
            settings.validate_settings(config)
        except settings.SettingsError as exc:
            self.status_label.setText(str(exc))
            return
        if not config.enabled or not config.api_key:
            self.status_label.setText("请先启用 LLM 并填写 API Key；测试不会保存设置。")
            return
        self.test_button.setEnabled(False)
        self.status_label.setText("正在测试当前填写的配置（不会保存）…")
        worker = _TestWorker(config)
        worker.signals.finished.connect(self._test_finished)
        self._worker = worker
        QThreadPool.globalInstance().start(worker)

    @Slot(bool)
    def _test_finished(self, success):
        self.test_button.setEnabled(True)
        self.status_label.setText("连接成功（测试未保存设置）。" if success else
                                  "连接失败，请检查网络、HTTPS 地址、模型及 API Key。")
        self._worker = None
