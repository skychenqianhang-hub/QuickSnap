"""Render the capture screen to PNG files (for checking the look without clicking).

    python tools_dev/preview_overlay.py OUT_DIR [lang]

Simulates: idle hint -> mouse drag -> toolbar shown. Saves overlay_*.png.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtGui import QCursor  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)
from app import capture, i18n  # noqa: E402
from app.overlay import CaptureSession  # noqa: E402

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
i18n.set_language(sys.argv[2] if len(sys.argv) > 2 else "en")

session = CaptureSession(capture.grab_all())
result = []
session.finished.connect(lambda a, img: result.append((a, img)))
session.start()
ov = session.overlays[0]
QTest.qWait(300)
QCursor.setPos(ov.mapToGlobal(QPoint(400, 300)))
QTest.mouseMove(ov, QPoint(400, 300))
QTest.qWait(100)
ov.grab().save(str(out / "overlay_1_idle.png"))

QTest.mousePress(ov, Qt.MouseButton.LeftButton, pos=QPoint(400, 300))
for i in range(1, 11):
    QTest.mouseMove(ov, QPoint(400 + 50 * i, 300 + 30 * i))
QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, pos=QPoint(900, 600))
QTest.qWait(200)
ov.grab().save(str(out / "overlay_2_selected.png"))
print("selection (real px):", ov.sel)

QTest.keyClick(ov, Qt.Key.Key_Return)
QTest.qWait(50)
print("result:", [(a, img.size()) for a, img in result])
session.close()
