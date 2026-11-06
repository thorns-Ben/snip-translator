"""Win32 窗口识别：Tab 悬停高亮顶层窗口。"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QGuiApplication

user32 = ctypes.WinDLL("user32", use_last_error=True)
try:
    dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
except OSError:  # pragma: no cover - 老系统
    dwmapi = None

GA_ROOT = 2
GW_HWNDNEXT = 2
DWMWA_EXTENDED_FRAME_BOUNDS = 9

_SKIP_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG), ("top", wintypes.LONG),
        ("right", wintypes.LONG), ("bottom", wintypes.LONG),
    ]


user32.WindowFromPoint.argtypes = [POINT]
user32.WindowFromPoint.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND
user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetWindow.restype = wintypes.HWND
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
user32.GetWindowRect.restype = wintypes.BOOL
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int

if dwmapi is not None:
    dwmapi.DwmGetWindowAttribute.argtypes = [
        wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD
    ]
    dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long


def _class_name(hwnd) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _frame_rect(hwnd) -> tuple[int, int, int, int] | None:
    if dwmapi is not None:
        rect = RECT()
        hr = dwmapi.DwmGetWindowAttribute(
            hwnd, DWMWA_EXTENDED_FRAME_BOUNDS,
            ctypes.byref(rect), ctypes.sizeof(rect),
        )
        if hr == 0 and rect.right > rect.left and rect.bottom > rect.top:
            return rect.left, rect.top, rect.right, rect.bottom
    rect = RECT()
    if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return rect.left, rect.top, rect.right, rect.bottom
    return None


def window_rect_at(global_logical_point: QPoint, geo: QRect, scale: float) -> QRect | None:
    """返回光标下方（跳过本程序遮罩）的顶层窗口，坐标为覆盖层本地逻辑坐标。"""
    if scale <= 0:
        return None
    screen = QGuiApplication.screenAt(global_logical_point) or QGuiApplication.primaryScreen()
    if screen is None:
        return None
    sg = screen.geometry()
    dpr = screen.devicePixelRatio()
    px = sg.x() + int(round((global_logical_point.x() - sg.x()) * dpr))
    py = sg.y() + int(round((global_logical_point.y() - sg.y()) * dpr))

    hwnd = user32.WindowFromPoint(POINT(px, py))
    if not hwnd:
        return None
    hwnd = user32.GetAncestor(hwnd, GA_ROOT) or hwnd

    own_pid = os.getpid()
    pid = wintypes.DWORD()
    seen = 0
    while hwnd and seen < 100:
        seen += 1
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value != own_pid and user32.IsWindowVisible(hwnd):
            cls = _class_name(hwnd)
            if cls not in _SKIP_CLASSES:
                r = _frame_rect(hwnd)
                if r is not None:
                    l, t, rr, b = r
                    if rr - l >= 8 and b - t >= 8 and l <= px < rr and t <= py < b:
                        return QRect(
                            sg.x() - geo.x() + int(round((l - sg.x()) / dpr)),
                            sg.y() - geo.y() + int(round((t - sg.y()) / dpr)),
                            max(1, int(round((rr - l) / dpr))),
                            max(1, int(round((b - t) / dpr))),
                        )
        hwnd = user32.GetWindow(hwnd, GW_HWNDNEXT)
    return None
