"""Thin ctypes wrappers around the public Windows APIs QuickSnap uses.

Everything here is a documented system call: screen copy (GDI BitBlt),
monitor geometry, RegisterHotKey, drive types, a named mutex.
No hooks, no injection, no keyboard logging.

All coordinates are physical pixels. Qt 6 makes the process
per-monitor-DPI-aware (v2) before any of this runs, so Windows reports
real pixel positions even with mixed scaling (100% / 150% ...).
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi")

# ---------------------------------------------------------------- monitors

MONITOR_DEFAULTTONEAREST = 2


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", wintypes.WCHAR * 32),
    ]


@dataclass(frozen=True)
class Monitor:
    handle: int
    left: int
    top: int
    right: int
    bottom: int
    primary: bool

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top


_MonitorEnumProc = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM
)
user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.c_void_p, _MonitorEnumProc, wintypes.LPARAM]
user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFOEXW)]
user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.MonitorFromWindow.restype = wintypes.HMONITOR


def _monitor_info(hmon) -> Monitor:
    info = MONITORINFOEXW()
    info.cbSize = ctypes.sizeof(MONITORINFOEXW)
    user32.GetMonitorInfoW(hmon, ctypes.byref(info))
    r = info.rcMonitor
    return Monitor(int(hmon or 0), r.left, r.top, r.right, r.bottom, bool(info.dwFlags & 1))


def list_monitors() -> list[Monitor]:
    found: list[Monitor] = []

    def cb(hmon, _hdc, _rect, _lp):
        found.append(_monitor_info(hmon))
        return True

    user32.EnumDisplayMonitors(None, None, _MonitorEnumProc(cb), 0)
    return found


def monitor_of_window(hwnd: int) -> Monitor:
    return _monitor_info(user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST))


# ---------------------------------------------------------------- screen copy

SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN, SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 76, 77, 78, 79
SRCCOPY = 0x00CC0020
CAPTUREBLT = 0x40000000
DIB_RGB_COLORS = 0


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


for _name, _args, _res in [
    ("GetDC", [wintypes.HWND], wintypes.HDC),
    ("ReleaseDC", [wintypes.HWND, wintypes.HDC], ctypes.c_int),
]:
    getattr(user32, _name).argtypes = _args
    getattr(user32, _name).restype = _res
for _name, _args, _res in [
    ("CreateCompatibleDC", [wintypes.HDC], wintypes.HDC),
    ("CreateCompatibleBitmap", [wintypes.HDC, ctypes.c_int, ctypes.c_int], wintypes.HBITMAP),
    ("SelectObject", [wintypes.HDC, wintypes.HGDIOBJ], wintypes.HGDIOBJ),
    ("BitBlt", [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD], wintypes.BOOL),
    ("GetDIBits", [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
                   ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT], ctypes.c_int),
    ("DeleteObject", [wintypes.HGDIOBJ], wintypes.BOOL),
    ("DeleteDC", [wintypes.HDC], wintypes.BOOL),
]:
    getattr(gdi32, _name).argtypes = _args
    getattr(gdi32, _name).restype = _res


def virtual_screen_rect() -> tuple[int, int, int, int]:
    """(left, top, width, height) of the whole desktop across all monitors."""
    g = user32.GetSystemMetrics
    return g(SM_XVIRTUALSCREEN), g(SM_YVIRTUALSCREEN), g(SM_CXVIRTUALSCREEN), g(SM_CYVIRTUALSCREEN)


def grab_rect(left: int, top: int, width: int, height: int) -> bytes:
    """Copy a desktop rectangle. Returns top-down BGRA bytes (width*height*4)."""
    screen_dc = user32.GetDC(None)
    mem_dc = gdi32.CreateCompatibleDC(screen_dc)
    bmp = gdi32.CreateCompatibleBitmap(screen_dc, width, height)
    old = gdi32.SelectObject(mem_dc, bmp)
    try:
        if not gdi32.BitBlt(mem_dc, 0, 0, width, height, screen_dc, left, top, SRCCOPY | CAPTUREBLT):
            raise OSError("BitBlt failed")
        bih = BITMAPINFOHEADER()
        bih.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bih.biWidth = width
        bih.biHeight = -height  # negative = top-down rows
        bih.biPlanes = 1
        bih.biBitCount = 32
        buf = ctypes.create_string_buffer(width * height * 4)
        # BITMAPINFO = header + colour table; 32-bit needs no table, but leave room.
        info = ctypes.create_string_buffer(ctypes.sizeof(BITMAPINFOHEADER) + 16)
        ctypes.memmove(info, ctypes.byref(bih), ctypes.sizeof(BITMAPINFOHEADER))
        gdi32.SelectObject(mem_dc, old)
        if not gdi32.GetDIBits(mem_dc, bmp, 0, height, buf, info, DIB_RGB_COLORS):
            raise OSError("GetDIBits failed")
        return buf.raw
    finally:
        gdi32.SelectObject(mem_dc, old)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(None, screen_dc)


# ---------------------------------------------------------------- hotkeys

WM_HOTKEY = 0x0312
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000

user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]


def register_hotkey(hwnd: int, hotkey_id: int, modifiers: int, vk: int) -> bool:
    return bool(user32.RegisterHotKey(hwnd, hotkey_id, modifiers | MOD_NOREPEAT, vk))


def unregister_hotkey(hwnd: int, hotkey_id: int) -> None:
    user32.UnregisterHotKey(hwnd, hotkey_id)


# ---------------------------------------------------------------- windows on screen

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x20
WS_EX_LAYERED = 0x80000
LWA_ALPHA = 0x2
DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14

_EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [_EnumWindowsProc, wintypes.LPARAM]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsIconic.argtypes = [wintypes.HWND]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.GetLayeredWindowAttributes.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD),
                                              ctypes.POINTER(ctypes.c_ubyte), ctypes.POINTER(wintypes.DWORD)]
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]

# The desktop background itself: clicking there means "whole screen", not a window.
_DESKTOP_CLASSES = {"Progman", "WorkerW"}


def cursor_pos() -> tuple[int, int]:
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]


def set_cursor_pos(x: int, y: int) -> None:
    """Move the mouse pointer (real pixels, desktop coordinates)."""
    user32.SetCursorPos(x, y)


def _visible_rect(hwnd) -> tuple[int, int, int, int] | None:
    """Window rectangle as you see it (without the invisible resize border Windows 10/11 adds)."""
    r = wintypes.RECT()
    if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(r), ctypes.sizeof(r)) != 0:
        if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
            return None
    if r.right - r.left <= 0 or r.bottom - r.top <= 0:
        return None
    return r.left, r.top, r.right, r.bottom


def list_windows(exclude_pid: int | None = None) -> list[tuple[int, int, int, int]]:
    """Rectangles (left, top, right, bottom) of visible top-level windows, topmost first.

    Skips minimised, hidden, click-through, fully transparent and "cloaked" windows
    (cloaked = apps on another virtual desktop or suspended store apps), and the desktop.
    """
    out: list[tuple[int, int, int, int]] = []
    cls = ctypes.create_unicode_buffer(64)

    def cb(hwnd, _lp):
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return True
        if exclude_pid is not None:
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == exclude_pid:
                return True
        cloaked = wintypes.DWORD()
        if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), 4) == 0 and cloaked.value:
            return True
        ex = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        if ex & WS_EX_TRANSPARENT:
            return True
        if ex & WS_EX_LAYERED:
            alpha, flags = ctypes.c_ubyte(255), wintypes.DWORD(0)
            if (user32.GetLayeredWindowAttributes(hwnd, None, ctypes.byref(alpha), ctypes.byref(flags))
                    and flags.value & LWA_ALPHA and alpha.value == 0):
                return True
        user32.GetClassNameW(hwnd, cls, 64)
        if cls.value in _DESKTOP_CLASSES:
            return True
        rect = _visible_rect(hwnd)
        if rect is not None:
            out.append(rect)
        return True

    user32.EnumWindows(_EnumWindowsProc(cb), 0)
    return out


# ---------------------------------------------------------------- misc

DRIVE_FIXED = 3
kernel32.GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
kernel32.GetLogicalDrives.restype = wintypes.DWORD


def fixed_drives() -> list[str]:
    """Letters of local hard drives, e.g. ['C', 'D']."""
    mask = kernel32.GetLogicalDrives()
    out = []
    for i in range(26):
        if mask & (1 << i):
            letter = chr(ord("A") + i)
            if kernel32.GetDriveTypeW(f"{letter}:\\") == DRIVE_FIXED:
                out.append(letter)
    return out


kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE
ERROR_ALREADY_EXISTS = 183
_mutex_handle = None


def claim_single_instance(name: str) -> bool:
    """True if we are the only running copy (keeps the mutex for the process lifetime)."""
    global _mutex_handle
    _mutex_handle = kernel32.CreateMutexW(None, False, name)
    return ctypes.get_last_error() != ERROR_ALREADY_EXISTS
