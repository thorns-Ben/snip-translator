"""Windows 全局热键：RegisterHotKey + Qt 原生事件过滤。

比 pynput 可靠 —— 不注入键盘钩子、不改按键状态，
Alt+字母 这种组合不会因为 Alt 影响字符映射而失效。
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal

WM_HOTKEY = 0x0312

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

VK_CODES = {
    **{chr(c): c for c in range(ord("A"), ord("Z") + 1)},
    **{str(d): 0x30 + d for d in range(10)},
    "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73,
    "F5": 0x74, "F6": 0x75, "F7": 0x76, "F8": 0x77,
    "F9": 0x78, "F10": 0x79, "F11": 0x7A, "F12": 0x7B,
    "SPACE": 0x20, "PRINT": 0x2C, "INSERT": 0x2D,
}

_MODS = {
    "alt": MOD_ALT,
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
}


def parse(spec: str):
    """'alt+d' -> (MOD_ALT|MOD_NOREPEAT, 0x44)"""
    parts = [p.strip().lower() for p in spec.replace("+", " ").split() if p.strip()]
    if not parts:
        raise ValueError(f"空热键: {spec!r}")

    *mods, key = parts
    flags = MOD_NOREPEAT
    for m in mods:
        if m not in _MODS:
            raise ValueError(f"未知修饰键: {m!r}")
        flags |= _MODS[m]

    key_name = key.upper()
    if key_name not in VK_CODES:
        raise ValueError(f"未知按键: {key!r}")
    return flags, VK_CODES[key_name]


class _Filter(QAbstractNativeEventFilter):
    def __init__(self, on_hotkey):
        super().__init__()
        self._on_hotkey = on_hotkey

    def nativeEventFilter(self, event_type, message):
        if event_type in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY:
                self._on_hotkey(int(msg.wParam))
                # 消费此消息，否则 Qt 分发到窗口时可能再次经过原生过滤器。
                return True, 0
        return False, 0


class HotkeyManager(QObject):
    """在指定窗口上注册全局热键。"""

    triggered = Signal(int)  # 热键 id

    def __init__(self, hwnd: int, parent=None):
        super().__init__(parent)
        self._hwnd = hwnd
        self._registered: dict[int, str] = {}
        self._filter = _Filter(self._on_hotkey)
        self._qapp = None
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._user32.RegisterHotKey.argtypes = [
            wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT
        ]
        self._user32.RegisterHotKey.restype = wintypes.BOOL
        self._user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        self._user32.UnregisterHotKey.restype = wintypes.BOOL

    def install(self, qapp) -> None:
        self._qapp = qapp
        qapp.installNativeEventFilter(self._filter)

    def uninstall(self) -> None:
        """退出时必须摘掉过滤器，否则 qapp 析构后仍会回调已销毁的对象。"""
        if self._qapp is not None:
            self._qapp.removeNativeEventFilter(self._filter)
            self._qapp = None

    def register(self, hotkey_id: int, spec: str) -> bool:
        try:
            mods, vk = parse(spec)
        except ValueError:
            return False
        ok = bool(
            self._user32.RegisterHotKey(
                wintypes.HWND(self._hwnd), hotkey_id, mods, vk
            )
        )
        if ok:
            self._registered[hotkey_id] = spec
        return ok

    def unregister_all(self) -> None:
        for hid in list(self._registered):
            self._user32.UnregisterHotKey(wintypes.HWND(self._hwnd), hid)
        self._registered.clear()
        self.uninstall()

    def _on_hotkey(self, hotkey_id: int):
        if hotkey_id in self._registered:
            self.triggered.emit(hotkey_id)
