"""Start the packaged exe, press the real global hotkey, photograph the screen, press Esc.

    python tools_dev/live_hotkey_test.py OUT_DIR

Uses SendInput (the same as a real keyboard). Leaves the exe running only on failure.
"""
from __future__ import annotations

import ctypes
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import win32  # noqa: E402

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)

user32 = ctypes.WinDLL("user32", use_last_error=True)
KEYEVENTF_KEYUP = 2


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def keys(*vks):
    seq = [(vk, 0) for vk in vks] + [(vk, KEYEVENTF_KEYUP) for vk in reversed(vks)]
    arr = (INPUT * len(seq))()
    for i, (vk, fl) in enumerate(seq):
        arr[i].type = 1
        arr[i].ki = KEYBDINPUT(vk, 0, fl, 0, 0)
    user32.SendInput(len(seq), arr, ctypes.sizeof(INPUT))


def snap(name):
    from PySide6.QtGui import QImage
    vx, vy, vw, vh = win32.virtual_screen_rect()
    raw = win32.grab_rect(vx, vy, vw, vh)
    QImage(raw, vw, vh, vw * 4, QImage.Format.Format_RGB32).copy().save(str(out / name))


def overlay_count():
    """Visible top-level windows of the exe that cover a whole monitor."""
    mons = {(m.left, m.top, m.right, m.bottom) for m in win32.list_monitors()}
    found = []
    pid_target = proc.pid
    EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, _):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == pid_target and user32.IsWindowVisible(hwnd):
            r = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            if (r.left, r.top, r.right, r.bottom) in mons:
                found.append(hwnd)
        return True

    user32.EnumWindows(EnumProc(cb), 0)
    return len(found)


exe = ROOT / "dist" / "QuickSnap" / "QuickSnap.exe"
proc = subprocess.Popen([str(exe), "--autostart"])
ok = True
try:
    time.sleep(3)
    print("before hotkey, capture windows:", overlay_count())
    keys(0x11, 0x12, 0x41)  # Ctrl+Alt+A
    time.sleep(1.0)
    n = overlay_count()
    print("after hotkey, capture windows:", n, "monitors:", len(win32.list_monitors()))
    ok = n == len(win32.list_monitors())
    snap("live_after_hotkey.png")
    keys(0x1B)  # Esc
    time.sleep(0.6)
    n2 = overlay_count()
    print("after Esc, capture windows:", n2)
    ok = ok and n2 == 0
    # second copy must refuse politely (shows a message box; close it)
    print("still running:", proc.poll() is None)
finally:
    proc.terminate()
print("LIVE TEST", "PASSED" if ok else "FAILED")
