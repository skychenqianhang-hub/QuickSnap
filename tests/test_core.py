"""Automatic tests that need no clicking. Run: python -m tests.test_core"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

os.environ["QUICKSNAP_CONFIG_DIR"] = tempfile.mkdtemp(prefix="quicksnap_test_")

from PySide6.QtCore import QPoint, QPointF, QRect  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from app import hotkey, i18n, win32  # noqa: E402
from app import selection as geo  # noqa: E402
from app.capture import MonitorShot  # noqa: E402
from app.config import Config, default_save_dir  # noqa: E402
from app.controller import unique_path  # noqa: E402
from app.overlay import CaptureSession  # noqa: E402

failures = 0


def check(name, cond):
    global failures
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        failures += 1


# --- hotkey text
check("parse Ctrl+Alt+A", hotkey.parse("Ctrl+Alt+A") == (win32.MOD_CONTROL | win32.MOD_ALT, 0x41))
check("parse F1", hotkey.parse("F1") == (0, 0x70))
check("normalize order/case", hotkey.normalize("shift+ctrl+prtsc") == "Ctrl+Shift+PrintScreen")
for bad in ["", "Ctrl+", "Ctrl+Alt", "Ctrl+Foo", "A+B"]:
    try:
        hotkey.parse(bad)
        check(f"reject {bad!r}", False)
    except ValueError:
        check(f"reject {bad!r}", True)

# --- default screenshot folder: avoid the system drive when possible
check("prefers D:", default_save_dir(["C", "D", "E"], "C") == Path("D:\\QuickSnap Screenshots"))
check("system drive not C", default_save_dir(["C", "D"], "D") == Path("C:\\QuickSnap Screenshots"))
check("only C -> Pictures", default_save_dir(["C"], "C") == Path.home() / "Pictures" / "QuickSnap")

# --- settings file
d = Path(tempfile.mkdtemp())
c = Config(d / "config.json")
c["hotkey"] = "Ctrl+Shift+X"
check("settings persist", Config(d / "config.json")["hotkey"] == "Ctrl+Shift+X")
(d / "broken.json").write_text("{not json", encoding="utf-8")
check("broken settings -> defaults", Config(d / "broken.json")["language"] == "en")

# --- file names
when = datetime(2026, 11, 7, 13, 25, 30)
p1 = unique_path(d, when)
check("file name", p1.name == "QuickSnap_2026-11-07_13-25-30.png")
p1.write_bytes(b"x")
check("no overwrite", unique_path(d, when).name == "QuickSnap_2026-11-07_13-25-30_2.png")

# --- translations complete
from tools_dev.i18n_check import collect  # noqa: E402

keys = collect()
for lang in ("zh", "ja"):
    table = i18n.load_table(lang)
    missing = [k for k in keys if k not in table]
    check(f"{lang} translations complete ({len(keys)} strings)", not missing)
    for k, v in table.items():
        check(f"{lang} placeholders match: {k[:30]!r}", k.count("{0}") == v.count("{0}")) if "{" in k else None

# --- selection maths on a fake 150%-scaled monitor (no real screen needed)
img = QImage(300, 200, QImage.Format.Format_RGB32)
img.fill(QColor("white"))
img.setPixelColor(150, 100, QColor("red"))
screen = app.primaryScreen()
fake_mon = win32.Monitor(0, 0, 0, 300, 200, True)
session = CaptureSession([MonitorShot(fake_mon, img)])
ov = session.overlays[0]
ov.shot = MonitorShot(fake_mon, img)
from PySide6.QtGui import QPixmap  # noqa: E402

ov._pix = QPixmap.fromImage(img)
ov.resize(200, 133)  # logical size of a 300x200 picture at 150%
sx, sy = ov._scale()
check("scale 1.5", abs(sx - 1.5) < 0.01)
check("to_real", ov.to_real(QPointF(100, 66.67)) == ov.to_real(QPointF(100, 66.67)) and
      ov.to_real(QPointF(100, 0)).x() == 150)
check("to_real clamps", ov.to_real(QPointF(-5, 999)) == ov.to_real(QPointF(0, 133)))
ov.sel = QRect(140, 90, 20, 20)
crop = ov.cropped()
check("crop size in real pixels", (crop.width(), crop.height()) == (20, 20))
check("crop content", crop.pixelColor(10, 10) == QColor("red"))
check("150%: pixel under mouse", ov.pixel_under(QPointF(100, 66.67)) == QPoint(150, 100))
check("150%: color of that pixel", ov.color_at(ov.pixel_under(QPointF(100, 66.67))) == "#FF0000")
check("pixel under mouse stays inside", ov.pixel_under(QPointF(5000, 5000)) == QPoint(299, 199))
ov.select_all()
check("select_all = whole screen", ov.cropped().size() == img.size())
session.close()

# --- magnifier placement: below-right, flips near edges, never off screen
check("magnifier below-right", geo.panel_position(QPointF(100, 100), 140, 170, 1920, 1080) == QPointF(120, 120))
check("magnifier flips left at right edge",
      geo.panel_position(QPointF(1850, 100), 140, 170, 1920, 1080) == QPointF(1690, 120))
check("magnifier flips up at bottom edge",
      geo.panel_position(QPointF(100, 1000), 140, 170, 1920, 1080) == QPointF(120, 810))
check("magnifier in bottom-right corner",
      geo.panel_position(QPointF(1900, 1070), 140, 170, 1920, 1080) == QPointF(1740, 880))
check("magnifier on a tiny screen stays on it",
      geo.panel_position(QPointF(50, 50), 140, 170, 100, 100) == QPointF(0, 0))

# --- stage 2: window under the mouse, resize, move
from app import selection as geo  # noqa: E402

whole = QRect(0, 0, 1920, 1080)
# desktop-wide rects, topmost first; monitor 2 sits right of monitor 1
wins = geo.windows_on_monitor([(100, 100, 500, 400), (0, 0, 1000, 800), (1900, 50, 2100, 300)],
                              0, 0, 1920, 1080)
check("windows clipped to monitor", wins[2] == QRect(1900, 50, 20, 250))
check("topmost window wins", geo.window_at(wins, QPoint(200, 200), whole) == QRect(100, 100, 400, 300))
check("window underneath", geo.window_at(wins, QPoint(900, 700), whole) == QRect(0, 0, 1000, 800))
check("empty desktop = whole screen", geo.window_at(wins, QPoint(1500, 1000), whole) == whole)
wins2 = geo.windows_on_monitor([(1900, 50, 2100, 300)], 1920, 0, 2560, 1440)
check("window on 2nd monitor", wins2 == [QRect(0, 50, 180, 250)])

check("from_corners exact size", geo.from_corners(10, 10, 110, 60) == QRect(10, 10, 100, 50))
check("from_corners reversed", geo.from_corners(110, 60, 10, 10) == QRect(10, 10, 100, 50))
box = QRect(100, 100, 200, 100)          # right edge at 300, bottom at 200 (exclusive)
check("resize right edge", geo.resize(box, "r", QPoint(350, 0), whole) == QRect(100, 100, 250, 100))
check("resize corner", geo.resize(box, "lt", QPoint(50, 80), whole) == QRect(50, 80, 250, 120))
check("resize past other side flips", geo.resize(box, "l", QPoint(400, 0), whole) == QRect(300, 100, 100, 100))
check("resize stops at screen", geo.resize(box, "rb", QPoint(5000, 5000), whole) == QRect(100, 100, 1820, 980))
check("move", geo.move(box, 10, -20, whole) == QRect(110, 80, 200, 100))
check("move stops at edge", geo.move(box, -999, 9999, whole) == QRect(0, 980, 200, 100))

from PySide6.QtCore import QRectF  # noqa: E402

lr = QRectF(100, 100, 200, 100)
check("hit corner", geo.hit_test(lr, QPointF(301, 199), 6) == "rb")
check("hit top edge", geo.hit_test(lr, QPointF(200, 97), 6) == "t")
check("hit inside = move", geo.hit_test(lr, QPointF(200, 150), 6) == "move")
check("hit outside", geo.hit_test(lr, QPointF(50, 50), 6) == "")
check("8 handles", len(geo.handle_points(lr)) == 8)

# --- simulated mouse on a real overlay window (fake 1:1 picture with two fake windows)
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

geo_screen = app.primaryScreen().geometry()
W, H = geo_screen.width(), geo_screen.height()
big = QImage(W, H, QImage.Format.Format_RGB32)
big.fill(QColor("gray"))
mon = win32.Monitor(0, geo_screen.x(), geo_screen.y(), geo_screen.x() + W, geo_screen.y() + H, True)
s2 = CaptureSession([], [(geo_screen.x() + 100, geo_screen.y() + 100, geo_screen.x() + 500,
                          geo_screen.y() + 400)])
ov = s2.overlays[0]
ov.set_shot(MonitorShot(mon, big))
ov.resize(W, H)
QTest.mouseClick(ov, Qt.MouseButton.LeftButton, pos=QPoint(200, 200))
check("click on window takes the window", ov.sel == QRect(100, 100, 400, 300))
QTest.mouseClick(ov, Qt.MouseButton.RightButton, pos=QPoint(200, 200))
check("right click clears", ov.sel is None)
QTest.mouseClick(ov, Qt.MouseButton.LeftButton, pos=QPoint(W - 50, H - 50))
check("click on desktop takes the screen", ov.sel == QRect(0, 0, W, H))
ov.clear_selection()
QTest.mousePress(ov, Qt.MouseButton.LeftButton, pos=QPoint(600, 500))
QTest.mouseMove(ov, QPoint(700, 560))
QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, pos=QPoint(700, 560))
check("drag draws a box", ov.sel == QRect(600, 500, 100, 60))
QTest.mousePress(ov, Qt.MouseButton.LeftButton, pos=QPoint(700, 560))   # bottom-right handle
QTest.mouseMove(ov, QPoint(750, 600))
QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, pos=QPoint(750, 600))
check("drag handle resizes", ov.sel == QRect(600, 500, 150, 100))
QTest.mousePress(ov, Qt.MouseButton.LeftButton, pos=QPoint(650, 550))   # inside
QTest.mouseMove(ov, QPoint(670, 540))
QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, pos=QPoint(670, 540))
check("drag inside moves", ov.sel == QRect(620, 490, 150, 100))
QTest.keyClick(ov, Qt.Key.Key_Right)
QTest.keyClick(ov, Qt.Key.Key_Down, Qt.KeyboardModifier.ShiftModifier)
check("arrow keys nudge", ov.sel == QRect(621, 500, 150, 100))
check("toolbar shown", ov.toolbar.isVisibleTo(ov))
check("no magnifier after picking", not ov.magnifier_visible())

# magnifier while hovering / drawing, colour + position, Ctrl+C copies the colour
from PySide6.QtCore import QEvent  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402


def hover(widget, pt):
    """Mouse move with no button pressed, delivered straight to a (hidden) test window."""
    ev = QMouseEvent(QEvent.Type.MouseMove, QPointF(pt), QPointF(widget.mapToGlobal(pt)),
                     Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(widget, ev)


ov.clear_selection()
big.setPixelColor(321, 123, QColor("#12AB34"))
ov.set_shot(MonitorShot(win32.Monitor(0, geo_screen.x() + 1920, geo_screen.y(), geo_screen.x() + 1920 + W,
                                      geo_screen.y() + H, False), big))
hover(ov, QPoint(321, 123))
check("magnifier while hovering", ov.magnifier_visible() and ov.cursor_px == QPoint(321, 123))
check("color under mouse", ov.color_at(ov.cursor_px) == "#12AB34")
check("normal arrow pointer (magnifier replaces the crosshair)",
      ov.cursor().shape() == Qt.CursorShape.ArrowCursor)
check("position is desktop-wide (2nd monitor)",
      ov.desktop_pos(ov.cursor_px) == QPoint(geo_screen.x() + 1920 + 321, geo_screen.y() + 123))
cb = app.clipboard()
saved_text = cb.text()
QTest.keyClick(ov, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
check("Ctrl+C copies the color", cb.text() == "#12AB34" and ov.sel is None)
cb.setText(saved_text)
img_shot = ov.grab()  # draws the magnifier; must not crash near any edge
for pt in [QPoint(2, 2), QPoint(W - 2, 2), QPoint(2, H - 2), QPoint(W - 2, H - 2)]:
    hover(ov, pt)
    ov.grab()
check("magnifier draws at all four corners", True)
QTest.mousePress(ov, Qt.MouseButton.LeftButton, pos=QPoint(300, 300))
QTest.mouseMove(ov, QPoint(400, 380))
check("magnifier while drawing a box", ov.magnifier_visible())
QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, pos=QPoint(400, 380))
QTest.mousePress(ov, Qt.MouseButton.LeftButton, pos=QPoint(350, 340))  # inside -> move
QTest.mouseMove(ov, QPoint(360, 350))
check("no magnifier while moving the box", not ov.magnifier_visible())
QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, pos=QPoint(360, 350))
s2.close()

print("\nALL PASSED" if not failures else f"\n{failures} FAILED")
sys.exit(1 if failures else 0)
