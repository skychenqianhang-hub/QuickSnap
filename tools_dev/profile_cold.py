"""Cost of the FIRST capture after QuickSnap starts, versus later ones.

    python tools_dev/profile_cold.py          # old way: windows built at each screenshot
    python tools_dev/profile_cold.py pool     # new way: built once at start-up, reused

Safe to run any time: shows no window, does not read the real screen, presses no keys.
It builds the capture screen on a made-up picture and draws it in memory (grab()).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

T = time.perf_counter
t_start = T()
from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtGui import QColor, QFontDatabase, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)
t_app = T()
from app import win32  # noqa: E402
from app.capture import MonitorShot  # noqa: E402
from app.overlay import CaptureSession, OverlayPool  # noqa: E402

t_import = T()
W, H = 1920, 1080
img = QImage(W, H, QImage.Format.Format_RGB32)
img.fill(QColor("#8899aa"))
shot = MonitorShot(win32.Monitor(0, 0, 0, W, H, True), img)
print(f"start-up: Qt {1000 * (t_app - t_start):.0f} ms, QuickSnap modules {1000 * (t_import - t_app):.0f} ms")
pool = None
if "pool" in sys.argv:
    tp = T()
    pool = OverlayPool()
    print(f"start-up: ready-made capture windows {1000 * (T() - tp):.0f} ms  (done once, before any hotkey)")


def one_round(label: str) -> None:
    t0 = T()
    session = CaptureSession([shot], [(100, 100, 900, 700)], pool=pool)
    ov = session.overlays[0]
    ov.set_shot(shot)
    ov.resize(W, H)
    t1 = T()
    ov.cursor_px = QPoint(400, 300)          # hint banner + magnifier (text drawing)
    ov.hover = ov.window_at(ov.cursor_px)
    ov.grab()
    t2 = T()
    ov.select(ov.hover)                      # toolbar with buttons
    ov.grab()
    t3 = T()
    session.close()
    app.processEvents()
    print(f"{label:12s} build windows {1000 * (t1 - t0):7.1f} ms | first drawing {1000 * (t2 - t1):7.1f} ms"
          f" | toolbar {1000 * (t3 - t2):7.1f} ms | total {1000 * (t3 - t0):7.1f} ms")


one_round("1st capture")
one_round("2nd capture")
one_round("3rd capture")
print(f"fonts installed: {len(QFontDatabase.families())} families")
