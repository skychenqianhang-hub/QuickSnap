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

# --- stage 3: shortcut checks
M = win32
check("text_from", hotkey.text_from(M.MOD_CONTROL | M.MOD_SHIFT, 0x58) == "Ctrl+Shift+X")
check("text_from unknown key", hotkey.text_from(M.MOD_CONTROL, 0xFF) is None)
check("bare letter rejected", hotkey.problem_with(0, 0x41) is not None)
check("Shift+letter rejected", hotkey.problem_with(M.MOD_SHIFT, 0x41) is not None)
check("Ctrl+Alt+A accepted", hotkey.problem_with(M.MOD_CONTROL | M.MOD_ALT, 0x41) is None)
check("Win+letter accepted", hotkey.problem_with(M.MOD_WIN | M.MOD_SHIFT, 0x41) is None)
check("F1 alone accepted", hotkey.problem_with(0, 0x70) is None)
check("PrintScreen alone accepted", hotkey.problem_with(0, 0x2C) is None)
check("Qt key -> VK letter", hotkey.vk_from_qt(int(Qt.Key.Key_X.value)) == 0x58)
check("Qt key -> VK F5", hotkey.vk_from_qt(int(Qt.Key.Key_F5.value)) == 0x74)
check("Qt key -> VK print", hotkey.vk_from_qt(int(Qt.Key.Key_Print.value)) == 0x2C)

# --- stage 3: start with Windows (uses a throw-away entry name, removed again)
from app import autostart  # noqa: E402

T = "QuickSnap-autotest"
autostart.disable(T)
check("autostart off at first", not autostart.is_enabled(T))
autostart.enable(T, r'"C:\Fake\QuickSnap.exe" --autostart')
check("autostart on", autostart.is_enabled(T))
check("autostart command stored", autostart.registered_command(T) == r'"C:\Fake\QuickSnap.exe" --autostart')
autostart.disable(T)
check("autostart off again", not autostart.is_enabled(T) and autostart.registered_command(T) is None)
check("autostart command (source run) uses pythonw + main.py",
      "pythonw.exe" in autostart.command() and "main.py" in autostart.command())

# --- stage 3: settings window with a stand-in controller
from PySide6.QtGui import QFocusEvent  # noqa: E402

from app.settings_window import SettingsWindow  # noqa: E402


class FakeController:
    def __init__(self):
        self.hotkey = "Ctrl+Alt+A"
        self.hotkey_ok = True
        self.paused = 0
        self.resumed = 0
        self.taken = {"Ctrl+Shift+Q"}  # pretend another program owns this one
        self.folder = Path(tempfile.mkdtemp())
        self.auto = False

    def hotkey_text(self): return self.hotkey
    def default_hotkey(self): return "Ctrl+Alt+A"
    def pause_hotkey(self): self.paused += 1
    def resume_hotkey(self): self.resumed += 1

    def set_hotkey(self, text):
        if text in self.taken:
            return "taken"
        self.hotkey = text
        return None

    def save_dir(self): return self.folder
    def set_save_dir(self, p): self.folder = Path(p)
    def open_folder(self): pass
    def autostart_enabled(self): return self.auto

    def set_autostart(self, on):
        self.auto = on

    def set_language(self, code): self.lang = code


def focus_in(w):
    QApplication.sendEvent(w, QFocusEvent(QEvent.Type.FocusIn, Qt.FocusReason.MouseFocusReason))


fc = FakeController()
for lang in ("en", "zh", "ja"):
    i18n.set_language(lang)
    sw = SettingsWindow(fc)
    check(f"settings window builds ({lang})", sw.hotkey_edit.text() == "Ctrl+Alt+A")
    sw.close()
i18n.set_language("en")
sw = SettingsWindow(fc)
ed = sw.hotkey_edit
focus_in(ed)
check("clicking the box pauses the old shortcut and asks for keys",
      fc.paused == 1 and ed.text() == "Press the new shortcut…")
QTest.keyClick(ed, Qt.Key.Key_A)
check("bare letter -> red message, nothing changed", fc.hotkey == "Ctrl+Alt+A" and "Ctrl" in sw.hotkey_status.text())
QTest.keyClick(ed, Qt.Key.Key_X, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
check("Ctrl+Shift+X chosen", fc.hotkey == "Ctrl+Shift+X" and ed.text() == "Ctrl+Shift+X")
focus_in(ed)
QTest.keyClick(ed, Qt.Key.Key_Q, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
check("taken combo -> message, old one kept", fc.hotkey == "Ctrl+Shift+X" and sw.hotkey_status.text() == "taken")
focus_in(ed)
QTest.keyClick(ed, Qt.Key.Key_Escape)
QApplication.sendEvent(ed, QFocusEvent(QEvent.Type.FocusOut, Qt.FocusReason.OtherFocusReason))
check("Esc keeps the current one", ed.text() == "Ctrl+Shift+X" and fc.resumed >= 1)
sw.autostart_box.setChecked(True)
check("auto-start checkbox calls through", fc.auto is True and sw.autostart_status.isVisibleTo(sw))
sw.close()

# --- stage 5a: drawing on the picture
from app import annotate  # noqa: E402

annotate.prefs.update({"color": "#FF3B30", "size": 1})
plain = QImage(W, H, QImage.Format.Format_RGB32)
plain.fill(QColor("#808080"))
s5 = CaptureSession([], [])
ov = s5.overlays[0]
ov.set_shot(MonitorShot(mon, plain))
ov.resize(W, H)
ov.select(QRect(100, 100, 400, 300))
ov.set_tool("rect")
check("tool picked: options strip shown", ov.options.isVisibleTo(ov) and ov.toolbar.tool_buttons["rect"].isChecked())
QTest.mousePress(ov, Qt.MouseButton.LeftButton, pos=QPoint(150, 150))
QTest.mouseMove(ov, QPoint(250, 220))
QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, pos=QPoint(250, 220))
check("drag draws a box", len(ov.shapes) == 1 and ov.shapes[0].kind == "rect")
img5 = ov.cropped()
check("copied picture keeps its size", (img5.width(), img5.height()) == (400, 300))
check("drawing is on the copied picture", img5.pixelColor(50, 85) == QColor("#FF3B30"))
check("inside the drawn box untouched", img5.pixelColor(100, 85) == QColor("#808080"))
check("box locked after drawing", ov.locked and ov._part_under(QPointF(500, 400)) == "")
QTest.mouseClick(ov, Qt.MouseButton.LeftButton, pos=QPoint(20, 20))
check("click outside the box keeps everything", ov.sel == QRect(100, 100, 400, 300) and len(ov.shapes) == 1)
QTest.mouseClick(ov, Qt.MouseButton.LeftButton, pos=QPoint(300, 300))
check("tiny click draws nothing", len(ov.shapes) == 1)
ov.set_tool("arrow")
QTest.mousePress(ov, Qt.MouseButton.LeftButton, pos=QPoint(300, 300))
QTest.mouseMove(ov, QPoint(450, 360))
QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, pos=QPoint(450, 360))
ov.set_tool("ellipse")
QTest.mousePress(ov, Qt.MouseButton.LeftButton, pos=QPoint(120, 300))
QTest.mouseMove(ov, QPoint(200, 380))
QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, pos=QPoint(200, 380))
ov.set_tool("pen")
QTest.mousePress(ov, Qt.MouseButton.LeftButton, pos=QPoint(130, 130))
for k in range(1, 8):
    QTest.mouseMove(ov, QPoint(130 + 10 * k, 130 + (k % 2) * 6))
QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, pos=QPoint(200, 130))
check("arrow, circle and pen drawn", [s.kind for s in ov.shapes] == ["rect", "arrow", "ellipse", "pen"])
check("pen keeps its path", len(ov.shapes[-1].points) >= 6)
QTest.mousePress(ov, Qt.MouseButton.LeftButton, pos=QPoint(480, 380))
QTest.mouseMove(ov, QPoint(900, 900))
QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, pos=QPoint(900, 900))
check("drawing stays inside the box", all(100 <= pt.x() <= 500 and 100 <= pt.y() <= 400
                                          for pt in ov.shapes[-1].points))
QTest.keyClick(ov, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
check("Ctrl+Z removes the last drawing", len(ov.shapes) == 4)
before = QRect(ov.sel)
QTest.keyClick(ov, Qt.Key.Key_Right)
check("arrow keys don't move a locked box", ov.sel == before)
ov.options._pick_color("#007AFF")
ov.options._pick_size(2)
ov.set_tool("rect")
QTest.mousePress(ov, Qt.MouseButton.LeftButton, pos=QPoint(300, 120))
QTest.mouseMove(ov, QPoint(360, 180))
QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, pos=QPoint(360, 180))
check("new colour and thickness used", ov.shapes[-1].color == "#007AFF" and ov.shapes[-1].width == 7.0)
QTest.mouseClick(ov, Qt.MouseButton.RightButton, pos=QPoint(300, 300))
check("first right-click puts the tool down, drawings stay", ov.tool is None and len(ov.shapes) == 5)
for _ in range(5):
    ov.undo()
check("undo everything unlocks the box", not ov.locked and ov._part_under(QPointF(500, 250)) == "r")
ov.set_tool("pen")
QTest.mouseClick(ov, Qt.MouseButton.LeftButton, pos=QPoint(250, 250))
QTest.mouseClick(ov, Qt.MouseButton.RightButton, pos=QPoint(250, 250))
QTest.mouseClick(ov, Qt.MouseButton.RightButton, pos=QPoint(250, 250))
check("second right-click picks again and drops the drawings", ov.sel is None and ov.shapes == [])
s5.close()

# 150% scaling: lines look the same thickness, drawings land on the right real pixels
annotate.prefs.update({"color": "#FF3B30", "size": 1})
small = QImage(300, 200, QImage.Format.Format_RGB32)
small.fill(QColor("#808080"))
s6 = CaptureSession([], [])
ov = s6.overlays[0]
ov.set_shot(MonitorShot(win32.Monitor(0, 0, 0, 300, 200, True), small))
ov.resize(200, 133)
ov.select(QRect(0, 0, 300, 200))
ov.set_tool("rect")
QTest.mousePress(ov, Qt.MouseButton.LeftButton, pos=QPoint(20, 20))
QTest.mouseMove(ov, QPoint(100, 80))
QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, pos=QPoint(100, 80))
sh = ov.shapes[0]
check("150%: line width in real pixels", abs(sh.width - 6.0) < 0.01)
check("150%: corners in real pixels", (round(sh.points[0].x()), round(sh.points[0].y())) == (30, 30)
      and (round(sh.points[1].x()), round(sh.points[1].y())) == (150, 120))
check("150%: drawing on the copied picture", ov.cropped().pixelColor(30, 75) == QColor("#FF3B30"))
s6.close()

# --- stage 5b: text and mosaic
annotate.prefs.update({"color": "#FFFFFF", "size": 1})
striped = QImage(W, H, QImage.Format.Format_RGB32)
striped.fill(QColor("#404040"))
for x in range(0, 600, 2):
    for y in range(300, 400):
        striped.setPixelColor(x, y, QColor("#E0E0E0"))
s7 = CaptureSession([], [])
done7 = []
s7.finished.connect(lambda a, im: done7.append(a))
ov = s7.overlays[0]
ov.set_shot(MonitorShot(mon, striped))
ov.resize(W, H)
ov.select(QRect(100, 100, 500, 300))
ov.set_tool("text")
check("text tool: sizes shown as letters", ov.options.size_buttons[0].toolTip() == "Small")
ed = ov.text_edit
QTest.mouseClick(ov, Qt.MouseButton.LeftButton, pos=QPoint(150, 150))
check("click opens the text box", ed.isVisibleTo(ov))
QTest.keyClicks(ed, "Hi")
QTest.keyClick(ed, Qt.Key.Key_Return)
check("Enter finishes the text", ov.shapes and ov.shapes[-1].kind == "text" and ov.shapes[-1].text == "Hi"
      and not ed.isVisibleTo(ov))
QTest.mouseClick(ov, Qt.MouseButton.LeftButton, pos=QPoint(150, 200))
ed.insertPlainText("你好世界")                      # what a Chinese input method delivers
QTest.mouseClick(ov, Qt.MouseButton.LeftButton, pos=QPoint(400, 200))
check("clicking elsewhere keeps the Chinese text", ov.shapes[-1].text == "你好世界" and ed.isVisibleTo(ov))
QTest.keyClicks(ed, "dropped")
QTest.keyClick(ed, Qt.Key.Key_Escape)
check("Esc drops only this text", len(ov.shapes) == 2 and not ed.isVisibleTo(ov) and done7 == [])
QTest.mouseClick(ov, Qt.MouseButton.LeftButton, pos=QPoint(150, 260))
QTest.keyClicks(ed, "a")
QTest.keyClick(ed, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
QTest.keyClicks(ed, "b")
ov.options._pick_color("#34C759")
check("colour change applies while typing", ed.color == "#34C759")
QTest.keyClick(ed, Qt.Key.Key_Return)
check("Shift+Enter makes a new line", ov.shapes[-1].text == "a\nb" and ov.shapes[-1].color == "#34C759")
QTest.mouseClick(ov, Qt.MouseButton.LeftButton, pos=QPoint(450, 120))
QTest.keyClicks(ed, "Z")
pic7 = ov.cropped()
check("copying while typing includes the text", ov.shapes[-1].text == "Z" and not ed.isVisibleTo(ov))
light = sum(pic7.pixelColor(x, y) == QColor("#FFFFFF") for x in range(40, 120) for y in range(30, 70))
check("text is on the copied picture", light > 20)
QTest.mouseClick(ov, Qt.MouseButton.LeftButton, pos=QPoint(450, 160))
QTest.keyClicks(ed, "x")
ov.undo()
check("undo while typing drops the text box first", not ed.isVisibleTo(ov) and ov.shapes[-1].text == "Z")
ov.set_tool("mosaic")
check("mosaic: no colour swatches", not ov.options.color_buttons[0][1].isVisibleTo(ov.options))
QTest.mousePress(ov, Qt.MouseButton.LeftButton, pos=QPoint(120, 350))
for k in range(1, 20):
    QTest.mouseMove(ov, QPoint(120 + 20 * k, 350))
QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, pos=QPoint(500, 350))
check("mosaic stroke kept", ov.shapes[-1].kind == "mosaic" and ov.shapes[-1].cell == annotate.MOSAIC_CELL)
pic7 = ov.cropped()
row = [pic7.pixelColor(x, 250).name() for x in range(40, 380)]
check("mosaic blurs the stripes into blocks", sum(a != b for a, b in zip(row, row[1:])) <= 50)
row_off = [pic7.pixelColor(x, 290).name() for x in range(40, 380)]
check("outside the stroke stays sharp", sum(a != b for a, b in zip(row_off, row_off[1:])) > 300)
ov.set_tool("rect")
check("box tool: colours back", ov.options.color_buttons[0][1].isVisibleTo(ov.options))
check("still no screenshot finished", done7 == [])
s7.close()

check("arrow head never longer than the arrow",
      annotate.arrow_geometry(QPointF(0, 0), QPointF(10, 0), 7)[1].boundingRect().width() <= 6.01)

# --- speed-up: ready-made capture windows are reused; pictures are not kept
from app.overlay import OverlayPool  # noqa: E402

pool = OverlayPool()
first_ids = [id(o) for o in pool.overlays]
results = []
for round_no in range(3):
    ses = CaptureSession([MonitorShot(mon, big)], [], pool=pool)
    ses.finished.connect(lambda a, im: results.append(a))
    ov = ses.overlays[0]
    ov.set_shot(MonitorShot(mon, big))
    check(f"pool round {round_no + 1}: starts clean", ov.sel is None and ov.hover is None and ov._mode is None
          and ov.shapes == [] and ov.tool is None and not ov.options.isVisibleTo(ov))
    if round_no == 0:
        ov.select(QRect(10, 10, 50, 40))
        ov.set_tool("pen")
        ov.shapes.append(annotate.Shape("pen", "#FF3B30", 4, [QPointF(20, 20)]))
    ov.select(QRect(10, 10, 50, 40))
    QTest.keyClick(ov, Qt.Key.Key_Return)
    ses.close()
    check(f"pool round {round_no + 1}: picture released", ov.shot is None and ov._pix.isNull())
check("pool: same windows reused", [id(o) for o in pool.overlays] == first_ids)
check("pool: one 'copy' per round (no doubled signals)", results == ["copy", "copy", "copy"])
pool.ensure_current()
check("pool: no rebuild when screens unchanged", [id(o) for o in pool.overlays] == first_ids)
pool.rebuild()
check("pool: rebuild makes new windows", [id(o) for o in pool.overlays] != first_ids)
pool.close()

# --- timing log
from app import timing  # noqa: E402

tm = timing.CaptureTimer("hotkey", 4, 12.5, True)
tm.mark("find windows")
tm.mark("screen copy")
line = tm.finish()
check("timing line has the steps", "find windows" in line and "TOTAL" in line and "key->program 4 ms" in line)
check("timing written once", tm.finish() == "" and timing.log_path().read_text(encoding="utf-8").count("TOTAL") >= 1)
for _ in range(2500):
    timing.write_line("x" * 60)
check("timing log stays small", timing.log_path().stat().st_size <= timing.MAX_BYTES + 200)

# --- stage 4: choices left by the installer (UTF-8 with BOM, Chinese folder name)
from app.config import installer_choices_path, take_installer_choices  # noqa: E402

cfg4 = Config(Path(tempfile.mkdtemp()) / "config.json")
ip = installer_choices_path()
ip.parent.mkdir(parents=True, exist_ok=True)
ip.write_bytes(b"\xef\xbb\xbf" + '{"save_dir": "E:\\\\截图\\\\QuickSnap", "language": "zh", "autostart": true}'
               .encode("utf-8"))
got = take_installer_choices(cfg4)
check("installer choices read", got.get("autostart") is True)
check("installer folder applied", cfg4["save_dir"] == "E:\\截图\\QuickSnap")
check("installer language applied", cfg4["language"] == "zh")
check("installer file removed", not ip.exists())
check("no installer file -> nothing", take_installer_choices(cfg4) == {})
ip.write_text("{broken", encoding="utf-8")
check("broken installer file ignored and removed",
      take_installer_choices(cfg4) == {} and cfg4["language"] == "zh" and not ip.exists())

print("\nALL PASSED" if not failures else f"\n{failures} FAILED")
sys.exit(1 if failures else 0)
