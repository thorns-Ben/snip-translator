"""Windows login autostart integration for JietuScreenshot.

This module only reads or changes the per-user Run value when its public
functions are called. Importing it never writes to the registry.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "JietuScreenshot"


def startup_command() -> str:
    """Return the command Windows should execute at login.

    Frozen applications use their executable directly. In source mode, use
    pythonw so a console is not opened and pass the repository's run.py by
    absolute path.
    """
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).resolve()
        return _quote(executable)

    pythonw = Path(sys.executable).resolve().with_name("pythonw.exe")
    root = Path(__file__).resolve().parent.parent
    return f"{_quote(pythonw)} -B {_quote(root / 'run.py')}"


def is_enabled() -> bool:
    """Return whether the Run value targets this current installation."""
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_READ) as key:
            value, _value_type = winreg.QueryValueEx(key, _VALUE_NAME)
    except (FileNotFoundError, OSError):
        return False
    return value == startup_command()


def set_enabled(enabled: bool) -> None:
    """Enable or disable login autostart for the current user."""
    import winreg

    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER,
        _RUN_KEY,
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        if enabled:
            winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, startup_command())
        else:
            try:
                winreg.DeleteValue(key, _VALUE_NAME)
            except FileNotFoundError:
                pass


def _quote(path: Path) -> str:
    """Quote a Windows path for a Run value."""
    return '"' + os.fspath(path).replace('"', '\\"') + '"'
