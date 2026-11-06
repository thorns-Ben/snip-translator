"""Isolated settings tests: temporary app data, synthetic keys, no real API calls."""

import dataclasses
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from jietu import llm_translate, settings


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {"LOCALAPPDATA": self.temp.name,
                                           "ZHIPU_API_KEY": ""})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.legacy = types.ModuleType("llm_config")
        self.modules = patch.dict(sys.modules, {"llm_config": self.legacy})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        # A hard network guard applies to every test, including GUI tests.
        guard = patch("urllib.request.OpenerDirector.open",
                      side_effect=AssertionError("unexpected network"))
        guard.start()
        self.addCleanup(guard.stop)

    def config(self, **values):
        return dataclasses.replace(settings.TranslationSettings(), **values)

    def test_path_defaults_and_immutability(self):
        self.assertEqual(settings.settings_path(),
                         Path(self.temp.name) / "JietuScreenshot" / "settings.json")
        config = settings.load_settings()
        self.assertEqual(config, self.config())
        with self.assertRaises(dataclasses.FrozenInstanceError):
            config.enabled = False
        self.assertNotIn("fake-secret", repr(self.config(api_key="fake-secret")))
        self.assertFalse(settings.settings_path().exists())

    def test_legacy_environment_and_frozen_priority(self):
        self.legacy.ZHIPU_API_KEY = "legacy-fake"
        self.legacy.ZHIPU_MODEL = "legacy-model"
        self.legacy.USE_LLM_TRANSLATION = False
        self.assertEqual(settings.load_settings(), self.config(
            api_key="legacy-fake", model="legacy-model", enabled=False))
        with patch.dict(os.environ, {"ZHIPU_API_KEY": "env-fake"}):
            self.assertEqual(settings.load_settings().api_key, "env-fake")
            with patch.object(sys, "frozen", True, create=True):
                self.assertEqual(settings.load_settings(), self.config(api_key="env-fake"))
        with patch.object(sys, "frozen", True, create=True):
            self.assertEqual(settings.load_settings(), self.config())

    def test_saved_disabled_and_empty_key_authoritative(self):
        self.legacy.ZHIPU_API_KEY = "legacy-fake"
        with patch.dict(os.environ, {"ZHIPU_API_KEY": "env-fake"}):
            saved = self.config(enabled=False, api_key="", model="saved-model")
            settings.save_settings(saved)
            self.assertEqual(settings.load_settings(), saved)
            self.assertFalse(llm_translate.is_available())
            settings.save_settings(self.config(enabled=True))
            self.assertEqual(llm_translate._load_key(), "")
            self.assertEqual(llm_translate._load_model(), settings.DEFAULT_MODEL)
            self.assertFalse(llm_translate.is_available())

    @unittest.skipUnless(sys.platform == "win32", "requires actual Windows DPAPI")
    def test_dpapi_round_trip_no_plaintext(self):
        config = self.config(api_key="synthetic-secret-测试")
        settings.save_settings(config)
        raw = settings.settings_path().read_text(encoding="utf-8")
        self.assertNotIn(config.api_key, raw)
        self.assertNotIn("synthetic-secret", raw)
        self.assertTrue(json.loads(raw)["api_key_dpapi"])
        self.assertEqual(settings.load_settings(), config)
        first = json.loads(raw)["api_key_dpapi"]
        settings.save_settings(config)
        self.assertNotEqual(json.loads(settings.settings_path().read_text(
            encoding="utf-8"))["api_key_dpapi"], first)

    def test_corrupt_and_decrypt_errors_sanitized_no_fallback(self):
        path = settings.settings_path()
        path.parent.mkdir(parents=True)
        cases = ["bad-json-secret", "[]", '{"version":1}',
                 json.dumps({"version": 1, "enabled": True,
                             "api_url": settings.DEFAULT_API_URL,
                             "model": settings.DEFAULT_MODEL,
                             "api_key_dpapi": "not base64 secret"})]
        self.legacy.ZHIPU_API_KEY = "legacy-fake"
        for raw in cases:
            path.write_text(raw, encoding="utf-8")
            with self.assertRaises(settings.SettingsError) as caught:
                settings.load_settings()
            self.assertNotIn("secret", str(caught.exception))
            self.assertIsNone(caught.exception.__cause__)
            self.assertFalse(llm_translate.is_available())
        settings.save_settings(self.config())
        obj = json.loads(path.read_text(encoding="utf-8"))
        obj["api_key_dpapi"] = "YWJj"
        path.write_text(json.dumps(obj), encoding="utf-8")
        with patch.object(settings, "_dpapi", side_effect=RuntimeError("private-key")):
            with self.assertRaises(settings.SettingsError) as caught:
                settings.load_settings()
            self.assertNotIn("private-key", str(caught.exception))

    def test_atomic_failure_retains_old_file_and_removes_temp(self):
        settings.save_settings(self.config(enabled=False))
        original = settings.settings_path().read_bytes()
        with patch.object(settings.os, "replace", side_effect=OSError("private details")):
            with self.assertRaises(settings.SettingsError) as caught:
                settings.save_settings(self.config(model="new-model"))
        self.assertNotIn("private details", str(caught.exception))
        self.assertEqual(settings.settings_path().read_bytes(), original)
        self.assertEqual(list(settings.settings_path().parent.iterdir()), [settings.settings_path()])
        with patch.object(settings, "_dpapi", side_effect=RuntimeError("secret")):
            with self.assertRaises(settings.SettingsError):
                settings.save_settings(self.config(api_key="fake"))
        self.assertEqual(settings.settings_path().read_bytes(), original)

    def test_validation(self):
        for url in ["http://example.com/api", "https://example.com", "https://user:pass@example.com/api",
                    "https://example.com/api?key=secret", "https://example.com/api#secret",
                    "https://example.com:bad/api", "https://example.com/a\nb"]:
            with self.assertRaises(settings.SettingsError):
                settings.save_settings(self.config(api_url=url))
        with self.assertRaises(settings.SettingsError):
            settings.save_settings(self.config(model=""))
        with self.assertRaises(settings.SettingsError):
            settings.save_settings(self.config(api_key="bad\nheader"))

    def test_requests_use_single_snapshot(self):
        config = self.config(api_url="https://example.test/chat/completions",
                             model="draft-model", api_key="fake")
        response = {"choices": [{"message": {"content": "name => 名称"}}]}
        for invoke in [lambda: llm_translate.translate("source"),
                       lambda: llm_translate.translate_identifiers(["name"])]:
            with patch.object(settings, "load_settings", return_value=config) as load, \
                    patch.object(llm_translate, "_http_post", return_value=response) as post:
                invoke()
                load.assert_called_once_with()
                args = post.call_args.args
                self.assertEqual(args[0], config.api_url)
                self.assertEqual(args[1]["model"], config.model)
                self.assertEqual(args[2], config.api_key)
        for config in [self.config(enabled=False, api_key="fake"), self.config()]:
            with patch.object(settings, "load_settings", return_value=config), \
                    patch.object(llm_translate, "_http_post") as post:
                with self.assertRaises(RuntimeError):
                    llm_translate.translate("text")
                with self.assertRaises(RuntimeError):
                    llm_translate.translate_identifiers(["name"])
                post.assert_not_called()

    def test_http_errors_and_payload_not_exposed(self):
        with self.assertRaises(RuntimeError) as caught:
            llm_translate._http_post(settings.DEFAULT_API_URL, {}, "fake", 1)
        self.assertNotIn("unexpected network", str(caught.exception))
        with patch.object(settings, "load_settings", return_value=self.config(api_key="fake")), \
                patch.object(llm_translate, "_http_post", return_value={"secret": "private"}):
            with self.assertRaises(RuntimeError) as caught:
                llm_translate.translate("text")
            self.assertNotIn("private", str(caught.exception))


class DialogTests(unittest.TestCase):
    setUp = SettingsTests.setUp
    config = SettingsTests.config

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_cancel_reopen_show_key_and_saved_signal(self):
        from PySide6.QtWidgets import QLineEdit
        from jietu.settings_dialog import SettingsDialog
        settings.save_settings(self.config(model="original"))
        old = settings.settings_path().read_bytes()
        dialog = SettingsDialog()
        self.addCleanup(dialog.close)
        dialog.show()
        self.app.processEvents()
        self.assertEqual(dialog.api_key_edit.echoMode(), QLineEdit.EchoMode.Password)
        dialog.show_key_check.setChecked(True)
        self.assertEqual(dialog.api_key_edit.echoMode(), QLineEdit.EchoMode.Normal)
        dialog.model_edit.setText("cancelled")
        dialog.reject()
        self.assertEqual(settings.settings_path().read_bytes(), old)
        dialog.show()
        self.app.processEvents()
        self.assertEqual(dialog.model_edit.text(), "original")
        self.assertEqual(dialog.api_key_edit.echoMode(), QLineEdit.EchoMode.Password)
        saved = Mock()
        dialog.saved.connect(saved)
        dialog.model_edit.setText("saved")
        dialog.accept()
        saved.assert_called_once_with()
        self.assertEqual(settings.load_settings().model, "saved")

    def test_open_cancel_does_not_create_settings(self):
        from jietu.settings_dialog import SettingsDialog
        dialog = SettingsDialog()
        dialog.reject()
        self.assertFalse(settings.settings_path().exists())

    def test_corrupt_dialog_and_failed_save_notice(self):
        from jietu.settings_dialog import SettingsDialog
        settings.settings_path().parent.mkdir(parents=True)
        settings.settings_path().write_text("private corrupt", encoding="utf-8")
        dialog = SettingsDialog()
        self.assertFalse(dialog.enabled_check.isChecked())
        self.assertTrue(dialog.status_label.text())
        self.assertNotIn("private", dialog.status_label.text())
        saved = Mock()
        dialog.saved.connect(saved)
        dialog.api_url_edit.setText("http://invalid")
        dialog.accept()
        saved.assert_not_called()
        dialog.reject()

    def test_draft_connection_and_generic_failure(self):
        from jietu.settings_dialog import test_connection
        config = self.config(api_key="synthetic-draft", model="draft-model")
        response = {"choices": [{"message": {"content": "OK"}}]}
        with patch.object(settings, "load_settings", side_effect=AssertionError("must use draft")), \
                patch.object(llm_translate, "_http_post", return_value=response) as post:
            self.assertTrue(test_connection(config))
            self.assertEqual(post.call_args.args[1]["model"], "draft-model")
            self.assertEqual(post.call_args.args[2:], ("synthetic-draft", 8))
        with patch.object(llm_translate, "_http_post", side_effect=RuntimeError("raw secret")):
            self.assertFalse(test_connection(config))
        self.assertFalse(settings.settings_path().exists())

    def test_async_button_draft_and_no_save(self):
        from PySide6.QtCore import QThreadPool
        from jietu.settings_dialog import SettingsDialog
        dialog = SettingsDialog()
        dialog.api_key_edit.setText("draft-secret")
        dialog.model_edit.setText("draft-model")
        with patch("jietu.settings_dialog.test_connection_detail",
                   return_value=(True, "连接成功（测试未保存设置）。")) as test:
            dialog._start_test()
            self.assertFalse(dialog.test_button.isEnabled())
            QThreadPool.globalInstance().waitForDone(3000)
            self.app.processEvents()
            self.assertTrue(dialog.test_button.isEnabled())
            self.assertIn("成功", dialog.status_label.text())
            self.assertEqual(test.call_args.args[0].model, "draft-model")
            self.assertFalse(settings.settings_path().exists())
        dialog.reject()


if __name__ == "__main__":
    unittest.main()
