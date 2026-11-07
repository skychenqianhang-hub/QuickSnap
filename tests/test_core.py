"""Automatic tests that need no clicking. Run: python -m tests.test_core"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

os.environ["QUICKSNAP_CONFIG_DIR"] = tempfile.mkdtemp(prefix="quicksnap_test_")

from PySide6.QtCore import QPointF, QRect  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from app import hotkey, i18n, win32  # noqa: E402
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
ov.select_all()
check("click = whole screen", ov.cropped().size() == img.size())
session.close()

print("\nALL PASSED" if not failures else f"\n{failures} FAILED")
sys.exit(1 if failures else 0)
