"""Where does the time go between the hotkey and a visible capture screen?

    python tools_dev/profile_capture.py [rounds]

Runs the same steps the app runs after the hotkey, several times, and prints
milliseconds per step. Opens and closes the capture screen on this PC each round.
"""
from __future__ import annotations

import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)
from app import capture, overlay, win32  # noqa: E402

rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 6
painted = {"t": None}
_orig_paint = overlay.Overlay.paintEvent


def timed_paint(self, e):
    _orig_paint(self, e)
    if painted["t"] is None:
        painted["t"] = time.perf_counter()


overlay.Overlay.paintEvent = timed_paint

rows = []
for i in range(rounds):
    painted["t"] = None
    t0 = time.perf_counter()
    wins = win32.list_windows(exclude_pid=os.getpid())
    t1 = time.perf_counter()
    vx, vy, vw, vh = win32.virtual_screen_rect()
    raw = win32.grab_rect(vx, vy, vw, vh)                      # the screen copy itself
    t2 = time.perf_counter()
    desktop = QImage(raw, vw, vh, vw * 4, QImage.Format.Format_RGB32).copy()
    shots = [capture.MonitorShot(m, desktop.copy(m.left - vx, m.top - vy, m.width, m.height))
             for m in win32.list_monitors()]
    t3 = time.perf_counter()
    session = overlay.CaptureSession(shots, wins)              # build the dimmed windows
    t4 = time.perf_counter()
    session.start()                                            # show them
    t5 = time.perf_counter()
    deadline = time.perf_counter() + 2
    while painted["t"] is None and time.perf_counter() < deadline:
        app.processEvents()
    t6 = painted["t"] or time.perf_counter()
    session.close()
    app.processEvents()
    time.sleep(0.3)
    if i == 0:
        continue  # first round includes one-off warm-up
    rows.append([(t1 - t0), (t2 - t1), (t3 - t2), (t4 - t3), (t5 - t4), (t6 - t5), (t6 - t0)])

names = ["find windows", "screen copy (BitBlt)", "picture conversion", "build capture windows",
         "show windows", "first drawing", "TOTAL (in program)"]
print(f"{len(wins)} windows, desktop {vw}x{vh}, {len(rows)} rounds (first warm-up round dropped)")
for k, n in enumerate(names):
    vals = [r[k] * 1000 for r in rows]
    print(f"{n:24s} median {statistics.median(vals):7.1f} ms   max {max(vals):7.1f} ms")
