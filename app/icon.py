"""The QuickSnap icon, drawn in code: a blue rounded square with white
crop-corner marks around a small dot (a viewfinder).  tools_dev/make_icon.py
writes the same drawing to app/assets/icon.ico for the .exe file."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap

SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def render(size: int) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = float(size)
    bg = QPainterPath()
    bg.addRoundedRect(QRectF(0.5, 0.5, s - 1, s - 1), s * 0.22, s * 0.22)
    p.fillPath(bg, QColor("#1E88E5"))
    pen = QPen(QColor("#FFFFFF"), max(1.5, s * 0.085))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    m, L = s * 0.24, s * 0.17   # margin, arm length
    a, b = m, s - m
    for (x, y, dx, dy) in [(a, a, 1, 1), (b, a, -1, 1), (a, b, 1, -1), (b, b, -1, -1)]:
        path = QPainterPath()
        path.moveTo(x + dx * L, y)
        path.lineTo(x, y)
        path.lineTo(x, y + dy * L)
        p.drawPath(path)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#FFFFFF"))
    r = s * 0.075
    p.drawEllipse(QRectF(s / 2 - r, s / 2 - r, 2 * r, 2 * r))
    p.end()
    return img


def app_icon() -> QIcon:
    icon = QIcon()
    for n in SIZES:
        icon.addPixmap(QPixmap.fromImage(render(n)))
    return icon
