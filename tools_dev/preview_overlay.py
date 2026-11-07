"""Render the capture screen to PNG files (for checking the look without clicking).

    python tools_dev/preview_overlay.py OUT_DIR [lang] [x y]

Uses the real windows on screen. Simulates: hover at (x, y) -> click there
(takes that window) -> drag a handle; also a fresh drag. Saves overlay_*.png.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)
from app import capture, i18n, win32  # noqa: E402
from app.overlay import CaptureSession  # noqa: E402

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
i18n.set_language(sys.argv[2] if len(sys.argv) > 2 else "en")
hx, hy = (int(sys.argv[3]), int(sys.argv[4])) if len(sys.argv) > 4 else (900, 400)

windows = win32.list_windows(exclude_pid=os.getpid())
session = CaptureSession(capture.grab_all(), windows)
session.start()
ov = session.overlays[0]
QTest.qWait(300)

QTest.mouseMove(ov, QPoint(hx, hy))
QTest.qWait(100)
ov.grab().save(str(out / "overlay_1_hover.png"))
print("hover:", ov.hover, "pixel:", ov.cursor_px)
QTest.mouseMove(ov, QPoint(ov.width() - 30, ov.height() - 30))
QTest.qWait(50)
ov.grab().save(str(out / "overlay_1b_corner.png"))
QTest.mouseMove(ov, QPoint(hx, hy))

QTest.mouseClick(ov, Qt.MouseButton.LeftButton, pos=QPoint(hx, hy))
QTest.qWait(100)
ov.grab().save(str(out / "overlay_2_clicked.png"))
print("clicked ->", ov.sel)

ov.clear_selection()
QTest.mousePress(ov, Qt.MouseButton.LeftButton, pos=QPoint(400, 300))
for i in range(1, 11):
    QTest.mouseMove(ov, QPoint(400 + 50 * i, 300 + 30 * i))
QTest.qWait(50)
ov.grab().save(str(out / "overlay_2b_drawing.png"))
QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, pos=QPoint(900, 600))
QTest.mouseMove(ov, QPoint(900, 600))
QTest.qWait(100)
ov.grab().save(str(out / "overlay_3_dragged.png"))
print("dragged ->", ov.sel)
session.close()
