"""End-to-end delay: press the real hotkey, time until the screen actually goes dark.

    python tools_dev/measure_latency.py [rounds] [exe]

Uses the QuickSnap that is already running (or starts `exe`). Each round: SendInput
Ctrl+Alt+A, then watch a small patch in the middle of the screen until it gets darker,
then Esc. Also notes when the capture window first exists. Prints milliseconds.
"""
from __future__ import annotations

import ctypes
import statistics
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import win32  # noqa: E402
from tools_dev._safety import refuse_if_gaming  # noqa: E402

refuse_if_gaming()  # never press keys while a game / anti-cheat is running

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32")


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def keys(*vks):
    seq = [(vk, 0) for vk in vks] + [(vk, 2) for vk in reversed(vks)]
    arr = (INPUT * len(seq))()
    for i, (vk, fl) in enumerate(seq):
        arr[i].type = 1
        arr[i].ki = KEYBDINPUT(vk, 0, fl, 0, 0)
    user32.SendInput(len(seq), arr, ctypes.sizeof(INPUT))


def brightness(x, y, n=24) -> float:
    raw = win32.grab_rect(x, y, n, n)
    return sum(raw[i] + raw[i + 1] + raw[i + 2] for i in range(0, len(raw), 4)) / (3 * n * n)


def capture_window_exists(pid) -> bool:
    mons = {(m.left, m.top, m.right, m.bottom) for m in win32.list_monitors()}
    found = []
    Proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, _):
        p = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid and user32.IsWindowVisible(hwnd):
            r = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            if (r.left, r.top, r.right, r.bottom) in mons:
                found.append(hwnd)
        return True

    user32.EnumWindows(Proc(cb), 0)
    return bool(found)


def running_pid():
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq QuickSnap.exe", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True).stdout
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) > 1 and parts[0].lower() == "quicksnap.exe":
            return int(parts[1])
    return None


rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 6
started = None
pid = running_pid()
if pid is None:
    exe = sys.argv[2] if len(sys.argv) > 2 else str(ROOT / "dist" / "QuickSnap" / "QuickSnap.exe")
    started = subprocess.Popen([exe, "--autostart"])
    pid = started.pid
    time.sleep(3)

mon = next(m for m in win32.list_monitors() if m.primary)
cx, cy = mon.left + mon.width // 2, mon.top + mon.height // 2
dark_ms, window_ms = [], []
try:
    for i in range(rounds):
        base = brightness(cx, cy)
        t0 = time.perf_counter()
        keys(0x11, 0x12, 0x41)  # Ctrl+Alt+A
        t_win = t_dark = None
        while time.perf_counter() - t0 < 3:
            now = time.perf_counter()
            if t_win is None and capture_window_exists(pid):
                t_win = now
            if brightness(cx, cy) < base * 0.85:
                t_dark = time.perf_counter()
                break
        keys(0x1B)  # Esc
        time.sleep(0.8)
        if t_dark is None:
            print(f"round {i + 1}: screen did not get darker (base brightness {base:.0f})")
            continue
        dark_ms.append((t_dark - t0) * 1000)
        window_ms.append(((t_win or t_dark) - t0) * 1000)
        print(f"round {i + 1}: window exists after {window_ms[-1]:6.0f} ms, screen dark after {dark_ms[-1]:6.0f} ms")
finally:
    if started is not None:
        started.terminate()
if dark_ms:
    print(f"MEDIAN: window {statistics.median(window_ms):.0f} ms, dark on screen {statistics.median(dark_ms):.0f} ms")
