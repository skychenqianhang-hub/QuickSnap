"""Drawing on a screenshot: boxes, circles, arrows and pen lines.

Every shape is stored in the monitor's real pixels (like the selection box), so the
saved picture gets crisp lines at 125% / 150% scaling too. The capture screen draws
shapes scaled down to Qt's logical coordinates; render() paints them 1:1 onto the
cropped picture that is copied / saved.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

TOOLS = ("rect", "ellipse", "arrow", "pen")
PALETTE = ["#FF3B30", "#FF9500", "#FFCC00", "#34C759", "#007AFF", "#AF52DE", "#FFFFFF", "#000000"]
SIZES = (2.0, 4.0, 7.0)   # thin / medium / thick, line width in logical pixels

# Last used colour / size, shared by all tools; the controller loads and saves them.
prefs = {"color": PALETTE[0], "size": 1}


@dataclass
class Shape:
    kind: str                     # one of TOOLS
    color: str                    # "#RRGGBB"
    width: float                  # line width in real pixels
    points: list[QPointF] = field(default_factory=list)  # rect/ellipse/arrow: [start, end]; pen: the path

    def is_meaningful(self) -> bool:
        """Leave out accidental clicks (a box or arrow of almost no size)."""
        if self.kind == "pen":
            return len(self.points) >= 1
        if len(self.points) < 2:
            return False
        a, b = self.points[0], self.points[-1]
        if self.kind == "arrow":
            return math.hypot(b.x() - a.x(), b.y() - a.y()) >= 4
        return abs(b.x() - a.x()) >= 2 and abs(b.y() - a.y()) >= 2


def _pen(s: Shape) -> QPen:
    pen = QPen(QColor(s.color), s.width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def arrow_geometry(a: QPointF, b: QPointF, width: float) -> tuple[QPointF, QPolygonF]:
    """Where the shaft ends and the triangle of the head, for an arrow from a to b."""
    dx, dy = b.x() - a.x(), b.y() - a.y()
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length                       # direction
    px, py = -uy, ux                                        # perpendicular
    head = min(max(10.0, width * 3.5 + 6.0), length * 0.6)  # head length, never longer than the arrow
    half = head * 0.42
    base = QPointF(b.x() - ux * head, b.y() - uy * head)
    tri = QPolygonF([b, QPointF(base.x() + px * half, base.y() + py * half),
                     QPointF(base.x() - px * half, base.y() - py * half)])
    shaft_end = QPointF(b.x() - ux * head * 0.8, b.y() - uy * head * 0.8)
    return shaft_end, tri


def paint_shape(p: QPainter, s: Shape) -> None:
    if not s.points:
        return
    p.setPen(_pen(s))
    p.setBrush(Qt.BrushStyle.NoBrush)
    a, b = s.points[0], s.points[-1]
    if s.kind == "rect":
        p.drawRect(QRectF(a, b).normalized())
    elif s.kind == "ellipse":
        p.drawEllipse(QRectF(a, b).normalized())
    elif s.kind == "arrow":
        shaft_end, tri = arrow_geometry(a, b, s.width)
        p.drawLine(a, shaft_end)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(s.color))
        p.drawPolygon(tri)
    elif s.kind == "pen":
        if len(s.points) == 1:
            p.drawPoint(a)
            return
        path = QPainterPath(s.points[0])
        for i in range(1, len(s.points) - 1):          # smooth curve through the midpoints
            mid = (s.points[i] + s.points[i + 1]) / 2
            path.quadTo(s.points[i], mid)
        path.lineTo(s.points[-1])
        p.drawPath(path)


def paint_shapes(p: QPainter, shapes) -> None:
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    for s in shapes:
        paint_shape(p, s)


def render(picture: QImage, shapes, offset: QPoint) -> QImage:
    """The cropped picture with the shapes painted on it. offset = where the crop starts."""
    out = picture.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    if shapes:
        p = QPainter(out)
        p.translate(-offset.x(), -offset.y())
        paint_shapes(p, shapes)
        p.end()
    return out.convertToFormat(QImage.Format.Format_RGB32)


# ---------------------------------------------------------------- toolbar icons


def tool_icon(kind: str, color: str = "#f2f2f2") -> QIcon:
    """Small white line icons drawn in code (crisp at any scaling)."""
    icon = QIcon()
    for scale in (1, 2):
        n = 18 * scale
        pm = QPixmap(n, n)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.scale(scale, scale)
        pen = QPen(QColor(color), 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        if kind == "rect":
            p.drawRect(QRectF(3, 4, 12, 10))
        elif kind == "ellipse":
            p.drawEllipse(QRectF(2.5, 4, 13, 10))
        elif kind == "arrow":
            p.drawLine(QPointF(4, 14), QPointF(13, 5))
            p.drawPolyline(QPolygonF([QPointF(8, 5), QPointF(13, 5), QPointF(13, 10)]))
        elif kind == "pen":
            path = QPainterPath(QPointF(3, 13))
            path.cubicTo(QPointF(6, 3), QPointF(9, 16), QPointF(15, 5))
            p.drawPath(path)
        elif kind == "undo":
            path = QPainterPath(QPointF(5, 7))
            path.lineTo(QPointF(11, 7))
            path.cubicTo(QPointF(16, 7), QPointF(16, 14), QPointF(11, 14))
            path.lineTo(QPointF(7, 14))
            p.drawPath(path)
            p.drawPolyline(QPolygonF([QPointF(8, 4), QPointF(5, 7), QPointF(8, 10)]))
        p.end()
        pm.setDevicePixelRatio(scale)
        icon.addPixmap(pm)
    return icon


def size_icon(index: int) -> QIcon:
    """A dot whose size shows thin / medium / thick."""
    icon = QIcon()
    for scale in (1, 2):
        n = 18 * scale
        pm = QPixmap(n, n)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.scale(scale, scale)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#f2f2f2"))
        r = (3.0, 5.0, 7.5)[index]
        p.drawEllipse(QPointF(9, 9), r / 2 + 1, r / 2 + 1)
        p.end()
        pm.setDevicePixelRatio(scale)
        icon.addPixmap(pm)
    return icon
