"""README screenshots on a made-up desktop (never the real screen, so nothing private shows).

    python tools_dev/make_screenshots.py            -> docs/screenshots/*-en.png, *-zh.png

Draws a simple desktop (wallpaper, a notes window, a chart window, a taskbar), puts the
real QuickSnap capture screen on top in a few states, and photographs the settings window.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)
from app import annotate, i18n, win32  # noqa: E402
from app.capture import MonitorShot  # noqa: E402
from app.overlay import CaptureSession  # noqa: E402
from app.settings_window import SettingsWindow  # noqa: E402

OUT = ROOT / "docs" / "screenshots"
W, H = 1920, 1080
NOTES = QRect(250, 150, 760, 560)
CHART = QRect(1080, 260, 640, 470)
TASKBAR = QRect(0, H - 48, W, 48)

TEXT = {
    "en": {"notes_title": "Notes — Weekend trip", "chart_title": "Monthly steps",
           "lines": ["Saturday", "• 8:30  Train to the lake (platform 4)", "• 10:00  Rent bikes at the pier",
                     "• 12:30  Lunch: noodle place by the bridge", "• 15:00  Museum, the photo exhibition",
                     "", "Sunday", "• Sunrise walk on the east trail", "• Pack the camera charger!",
                     "• Send the photos to everyone"],
           "months": ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]},
    "zh": {"notes_title": "笔记 — 周末出游", "chart_title": "每月步数",
           "lines": ["周六", "• 8:30  坐火车去湖边（4 号站台）", "• 10:00  码头租自行车",
                     "• 12:30  午饭：桥边那家面馆", "• 15:00  博物馆摄影展", "", "周日",
                     "• 早起去东边步道看日出", "• 别忘了带相机充电器！", "• 把照片发给大家"],
           "months": ["1月", "2月", "3月", "4月", "5月", "6月"]},
}


def window_frame(p: QPainter, r: QRect, title: str) -> QRect:
    """Draw a plain light window; returns the content rectangle."""
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 40))
    p.drawRoundedRect(QRectF(r.adjusted(-2, 2, 4, 8)), 10, 10)        # soft shadow
    path = QPainterPath()
    path.addRoundedRect(QRectF(r), 8, 8)
    p.fillPath(path, QColor("#ffffff"))
    p.fillRect(QRect(r.left(), r.top() + 8, r.width(), 32), QColor("#f3f3f3"))
    top = QPainterPath()
    top.addRoundedRect(QRectF(r.left(), r.top(), r.width(), 20), 8, 8)
    p.fillPath(top, QColor("#f3f3f3"))
    f = QFont("Segoe UI", 10)
    p.setFont(f)
    p.setPen(QColor("#333333"))
    p.drawText(QRect(r.left() + 16, r.top(), r.width() - 140, 40), Qt.AlignmentFlag.AlignVCenter, title)
    p.setPen(QColor("#666666"))
    for i, ch in enumerate(["—", "☐", "✕"]):
        p.drawText(QRect(r.right() - 130 + i * 44, r.top(), 44, 40), Qt.AlignmentFlag.AlignCenter, ch)
    return QRect(r.left(), r.top() + 40, r.width(), r.height() - 40)


def desktop(lang: str) -> QImage:
    t = TEXT[lang]
    img = QImage(W, H, QImage.Format.Format_RGB32)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    g = QLinearGradient(0, 0, W, H)
    g.setColorAt(0, QColor("#7fb2e5"))
    g.setColorAt(0.55, QColor("#a7c7e7"))
    g.setColorAt(1, QColor("#f3d9c4"))
    p.fillRect(img.rect(), g)
    p.setPen(Qt.PenStyle.NoPen)                                            # gentle hills
    p.setBrush(QColor(255, 255, 255, 50))
    p.drawEllipse(QRectF(-300, 700, 1400, 700))
    p.setBrush(QColor(255, 255, 255, 35))
    p.drawEllipse(QRectF(900, 760, 1500, 700))

    c = window_frame(p, NOTES, t["notes_title"])
    p.setFont(QFont("Segoe UI", 13))
    y = c.top() + 30
    for i, line in enumerate(t["lines"]):
        bold = line and not line.startswith("•")
        f = QFont("Segoe UI", 13 if not bold else 14)
        f.setBold(bool(bold))
        p.setFont(f)
        p.setPen(QColor("#1e5aa8") if bold else QColor("#222222"))
        p.drawText(QPoint(c.left() + 36, y), line)
        y += 44

    c = window_frame(p, CHART, t["chart_title"])
    values = [5.2, 6.8, 6.1, 8.4, 9.6, 7.3]
    colors = ["#4e79a7", "#59a14f", "#f28e2b", "#e15759", "#76b7b2", "#edc948"]
    base = c.bottom() - 60
    p.setPen(QColor("#dddddd"))
    for k in range(5):
        yy = base - k * 70
        p.drawLine(c.left() + 50, yy, c.right() - 30, yy)
    bw = 62
    for i, v in enumerate(values):
        x = c.left() + 80 + i * 86
        h = int(v * 33)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(colors[i]))
        p.drawRoundedRect(QRectF(x, base - h, bw, h), 4, 4)
        p.setPen(QColor("#555555"))
        p.setFont(QFont("Segoe UI", 11))
        p.drawText(QRect(x - 10, base + 8, bw + 20, 30), Qt.AlignmentFlag.AlignCenter, t["months"][i])

    p.fillRect(TASKBAR, QColor(32, 32, 36, 235))                            # taskbar
    for i in range(6):
        p.setBrush(QColor(255, 255, 255, 60 if i else 140))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(W / 2 - 150 + i * 52, H - 38, 30, 30), 6, 6)
    p.end()
    return img


def window_rects():
    rs = [NOTES, CHART, TASKBAR]  # topmost first; the desktop itself = whole screen
    return [(r.left(), r.top(), r.left() + r.width(), r.top() + r.height()) for r in rs]


def capture_states(lang: str) -> None:
    shot = MonitorShot(win32.Monitor(0, 0, 0, W, H, True), desktop(lang))
    session = CaptureSession([shot], window_rects())
    ov = session.overlays[0]
    ov.setGeometry(0, 0, W, H)
    ov.set_shot(shot)
    ov.resize(W, H)
    QTest.qWait(50)

    # 1) hovering over the notes window: it lights up, magnifier on the text
    ov.cursor_px = QPoint(452, 300)
    ov.hover = ov.window_at(ov.cursor_px)
    ov.grab().save(str(OUT / f"capture-window-{lang}.png"))

    # 2) dragging a box around the chart bars, magnifier at the corner
    ov.hover = None
    ov._mode = "new"
    ov._press = QPoint(1140, 360)
    ov.cursor_px = QPoint(1632, 694)
    ov.sel = QRect(1140, 360, 492, 334)
    ov.grab().save(str(OUT / f"capture-drag-{lang}.png"))

    # 3) box picked: handles + toolbar + hint banner
    ov.cursor_px = None
    ov.select(QRect(1140, 360, 520, 352))
    QTest.qWait(50)
    ov.grab().save(str(OUT / f"capture-selected-{lang}.png"))

    # 4) drawing: a circle around the tallest bar, an arrow pointing at it, a box, a pen underline
    ov.select(QRect(1110, 320, 600, 400))
    annotate.prefs.update({"color": "#FF3B30", "size": 1})
    ov.set_tool("ellipse")
    ov.shapes = [
        annotate.Shape("ellipse", "#FF3B30", 4, [QPointF(1488, 335), QPointF(1582, 700)]),
        annotate.Shape("arrow", "#FF3B30", 4, [QPointF(1300, 400), QPointF(1478, 470)]),
        annotate.Shape("rect", "#FFCC00", 4, [QPointF(1145, 488), QPointF(1235, 712)]),
        annotate.Shape("pen", "#007AFF", 4, [QPointF(1500 + k * 6, 712 + (3 if k % 2 else -3))
                                             for k in range(12)]),
    ]
    ov.toolbar.undo_button.setEnabled(True)
    QTest.qWait(50)
    ov.grab().save(str(OUT / f"capture-draw-{lang}.png"))
    ov.cropped().save(str(OUT / f"result-draw-{lang}.png"))   # what gets copied / saved
    session.close()


class Stand:  # settings window without touching real settings
    hotkey_ok = True
    def hotkey_text(self): return "Ctrl+Alt+A"
    def default_hotkey(self): return "Ctrl+Alt+A"
    def save_dir(self): return Path("D:/QuickSnap Screenshots")
    def autostart_enabled(self): return True
    def __getattr__(self, _): return lambda *a, **k: None


def settings_shot(lang: str) -> None:
    w = SettingsWindow(Stand())
    w.show()
    QTest.qWait(200)
    w.grab().save(str(OUT / f"settings-{lang}.png"))
    w.close()


OUT.mkdir(parents=True, exist_ok=True)
for lang in ("en", "zh"):
    i18n.set_language(lang)
    capture_states(lang)
    settings_shot(lang)
for f in sorted(OUT.glob("*.png")):
    print(f.name, f.stat().st_size // 1024, "KB")
