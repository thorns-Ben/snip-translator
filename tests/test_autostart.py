from __future__ import annotations

import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class AutostartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.autostart = importlib.import_module("jietu.autostart")

    def test_source_startup_command_uses_pythonw_and_absolute_run_path(self):
        with patch.object(self.autostart.sys, "frozen", False, create=True), patch.object(
            self.autostart.sys, "executable", r"C:\Python\python.exe"
        ):
            command = self.autostart.startup_command()
        self.assertEqual(
            command, '"C:\\Python\\pythonw.exe" -B "D:\\MLY26\\桌面\\jietu\\run.py"'
        )

    def test_frozen_startup_command_is_quoted_executable(self):
        with patch.object(self.autostart.sys, "frozen", True, create=True), patch.object(
            self.autostart.sys, "executable", r"C:\Program Files\Jietu\截图识字.exe"
        ):
            self.assertEqual(
                self.autostart.startup_command(), '"C:\\Program Files\\Jietu\\截图识字.exe"'
            )

    def test_import_does_not_touch_registry(self):
        with patch.dict(sys.modules, {"winreg": None}):
            importlib.reload(self.autostart)

    def test_is_enabled_reads_only_the_named_value(self):
        key = Mock()
        key.__enter__ = Mock(return_value=key)
        key.__exit__ = Mock(return_value=False)
        winreg = types.SimpleNamespace(
            HKEY_CURRENT_USER=object(), KEY_READ=1, OpenKey=Mock(return_value=key),
            QueryValueEx=Mock(return_value=(self.autostart.startup_command(), 1)),
        )
        with patch.dict(sys.modules, {"winreg": winreg}):
            self.assertTrue(self.autostart.is_enabled())
        winreg.OpenKey.assert_called_once_with(
            winreg.HKEY_CURRENT_USER, self.autostart._RUN_KEY, 0, winreg.KEY_READ
        )

    def test_is_enabled_rejects_stale_command(self):
        key = Mock()
        key.__enter__ = Mock(return_value=key)
        key.__exit__ = Mock(return_value=False)
        winreg = types.SimpleNamespace(
            HKEY_CURRENT_USER=object(), KEY_READ=1, OpenKey=Mock(return_value=key),
            QueryValueEx=Mock(return_value=('"C:\\old\\截图识字.exe"', 1)),
        )
        with patch.dict(sys.modules, {"winreg": winreg}):
            self.assertFalse(self.autostart.is_enabled())

    def test_set_enabled_true_writes_run_value_without_real_registry(self):
        key = Mock()
        key.__enter__ = Mock(return_value=key)
        key.__exit__ = Mock(return_value=False)
        winreg = types.SimpleNamespace(
            HKEY_CURRENT_USER=object(), KEY_SET_VALUE=2, REG_SZ=1,
            CreateKeyEx=Mock(return_value=key), SetValueEx=Mock(),
        )
        with patch.dict(sys.modules, {"winreg": winreg}):
            self.autostart.set_enabled(True)
        winreg.SetValueEx.assert_called_once_with(
            key, "JietuScreenshot", 0, winreg.REG_SZ, self.autostart.startup_command()
        )

    def test_set_enabled_false_deletes_value_and_ignores_missing(self):
        key = Mock()
        key.__enter__ = Mock(return_value=key)
        key.__exit__ = Mock(return_value=False)
        winreg = types.SimpleNamespace(
            HKEY_CURRENT_USER=object(), KEY_SET_VALUE=2,
            CreateKeyEx=Mock(return_value=key),
            DeleteValue=Mock(side_effect=FileNotFoundError),
        )
        with patch.dict(sys.modules, {"winreg": winreg}):
            self.autostart.set_enabled(False)
        winreg.DeleteValue.assert_called_once_with(key, "JietuScreenshot")


if __name__ == "__main__":
    unittest.main()
