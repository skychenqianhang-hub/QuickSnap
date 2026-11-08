"""Drawing on a screenshot: boxes, circles, arrows, pen lines, text and mosaic.

Every shape is stored in the monitor's real pixels (like the selection box), so the
saved picture gets crisp results at 125% / 150% scaling too. The capture screen draws
shapes scaled down to Qt's logical coordinates; render() paints them 1:1 onto the
picked area that is copied / saved.

Mosaic blocks are lined up with the whole monitor (not with the box), so the blocks on
screen and in the saved picture are exactly the same.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QFontMetricsF, QIcon, QImage, QPainter, QPainterPath,
                           QPainterPathStroker, QPen, QPixmap, QPolygonF)

TOOLS = ("rect", "ellipse", "arrow", "pen", "text", "mosaic")
PALETTE = ["#FF3B30", "#FF9500", "#FFCC00", "#34C759", "#007AFF", "#AF52DE", "#FFFFFF", "#000000"]
SIZES = (2.0, 4.0, 7.0)            # thin / medium / thick: line width, logical pixels
TEXT_SIZES = (16.0, 22.0, 30.0)    # small / medium / large: font size, logical pixels
MOSAIC_SIZES = (16.0, 28.0, 44.0)  # thin / medium / thick: brush width, logical pixels
MOSAIC_CELL = 8.0                  # size of one mosaic block, logical pixels

# Last used colour / size, shared by all tools; the controller loads and saves them.
prefs = {"color": PALETTE[0], "size": 1}


@dataclass
class Shape:
    kind: str                     # one of TOOLS
    color: str                    # "#RRGGBB" (not used by mosaic)
    width: float                  # real pixels: line width / font size (text) / brush width (mosaic)
    points: list[QPointF] = field(default_factory=list)
    # rect/ellipse/arrow: [start, end]; pen/mosaic: the path; text: [top-left]
    text: str = ""                # text only
    cell: float = 0.0             # mosaic only: block size in real pixels

    def is_meaningful(self) -> bool:
        """Leave out accidental clicks (a box or arrow of almost no size, empty text)."""
        if self.kind == "text":
            return bool(self.text.strip()) and bool(self.points)
        if self.kind in ("pen", "mosaic"):
            return len(self.points) >= 1
        if len(self.points) < 2:
            return False
        a, b = self.points[0], self.points[-1]
        if self.kind == "arrow":
            return math.hypot(b.x() - a.x(), b.y() - a.y()) >= 4
        return abs(b.x() - a.x()) >= 2 and abs(b.y() - a.y()) >= 2


def text_font(pixel_size: float) -> QFont:
    """The font used for text both while typing and in the saved picture."""
    f = QFont()
    f.setPixelSize(max(1, round(pixel_size)))
    return f


def _pen(s: Shape) -> QPen:
    pen = QPen(QColor(s.color), s.width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _smooth_path(points: list[QPointF]) -> QPainterPath:
    path = QPainterPath(points[0])
    if len(points) == 1:
        path.lineTo(points[0] + QPointF(0.01, 0))        # a dot still has a (round) shape
        return path
    for i in range(1, len(points) - 1):                  # smooth curve through the midpoints
        mid = (points[i] + points[i + 1]) / 2
        path.quadTo(points[i], mid)
    path.lineTo(points[-1])
    return path


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


# ---------------------------------------------------------------- mosaic

_pixel_cache: dict[tuple[int, int], QImage] = {}


def pixelated(base: QImage, cell: float) -> QImage:
    """The whole monitor picture turned into blocks of `cell` real pixels (cached per picture)."""
    c = max(2, round(cell))
    key = (base.cacheKey(), c)
    img = _pixel_cache.get(key)
    if img is None:
        if len(_pixel_cache) > 6:
            _pixel_cache.clear()
        w, h = base.width(), base.height()
        small = base.scaled(max(1, math.ceil(w / c)), max(1, math.ceil(h / c)),
                            Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        img = small.scaled(small.width() * c, small.height() * c,
                           Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation)
        _pixel_cache[key] = img
    return img


def mosaic_area(s: Shape) -> QPainterPath:
    """The area a mosaic stroke covers."""
    stroker = QPainterPathStroker()
    stroker.setWidth(s.width)
    stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
    stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return stroker.createStroke(_smooth_path(s.points))


# ---------------------------------------------------------------- painting


def paint_shape(p: QPainter, s: Shape, base: QImage | None = None) -> None:
    if not s.points:
        return
    a, b = s.points[0], s.points[-1]
    if s.kind == "mosaic":
        if base is None:
            return
        p.save()
        p.setClipPath(mosaic_area(s), Qt.ClipOperation.IntersectClip)
        p.drawImage(QPointF(0, 0), pixelated(base, s.cell))
        p.restore()
        return
    if s.kind == "text":
        font = text_font(s.width)
        fm = QFontMetricsF(font)
        p.setFont(font)
        p.setPen(QColor(s.color))
        for i, line in enumerate(s.text.split("\n")):
            p.drawText(QPointF(a.x(), a.y() + fm.ascent() + i * fm.lineSpacing()), line)
        return
    p.setPen(_pen(s))
    p.setBrush(Qt.BrushStyle.NoBrush)
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
        else:
            p.drawPath(_smooth_path(s.points))


def paint_shapes(p: QPainter, shapes, base: QImage | None = None) -> None:
    """Paint in drawing order. `base` = the monitor picture (needed for mosaic),
    in the same coordinates as the shapes."""
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    for s in shapes:
        paint_shape(p, s, base)


def render(base: QImage, shapes, crop: QRect) -> QImage:
    """The picked area `crop` of the monitor picture `base`, with the shapes painted on it."""
    out = base.copy(crop).convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    if shapes:
        p = QPainter(out)
        p.translate(-crop.x(), -crop.y())
        paint_shapes(p, shapes, base)
        p.end()
    return out.convertToFormat(QImage.Format.Format_RGB32)


# ---------------------------------------------------------------- toolbar icons


def _icon(draw) -> QIcon:
    icon = QIcon()
    for scale in (1, 2):
        n = 18 * scale
        pm = QPixmap(n, n)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.scale(scale, scale)
        draw(p)
        p.end()
        pm.setDevicePixelRatio(scale)
        icon.addPixmap(pm)
    return icon


def tool_icon(kind: str, color: str = "#f2f2f2") -> QIcon:
    """Small white line icons drawn in code (crisp at any scaling)."""
    def draw(p: QPainter):
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
        elif kind == "text":
            p.drawPolyline(QPolygonF([QPointF(4, 15), QPointF(9, 3), QPointF(14, 15)]))
            p.drawLine(QPointF(6, 11), QPointF(12, 11))
        elif kind == "mosaic":
            p.setPen(Qt.PenStyle.NoPen)
            for i in range(3):
                for j in range(3):
                    p.setBrush(QColor(color) if (i + j) % 2 == 0 else QColor(130, 130, 130))
                    p.drawRect(QRectF(3 + i * 4, 3 + j * 4, 4, 4))
        elif kind == "undo":
            path = QPainterPath(QPointF(5, 7))
            path.lineTo(QPointF(11, 7))
            path.cubicTo(QPointF(16, 7), QPointF(16, 14), QPointF(11, 14))
            path.lineTo(QPointF(7, 14))
            p.drawPath(path)
            p.drawPolyline(QPolygonF([QPointF(8, 4), QPointF(5, 7), QPointF(8, 10)]))
    return _icon(draw)


def size_icon(index: int, kind: str = "line") -> QIcon:
    """Thin / medium / thick as a dot of growing size; for text a growing letter A."""
    def draw(p: QPainter):
        if kind == "text":
            p.setPen(QColor("#f2f2f2"))
            f = QFont()
            f.setPixelSize((9, 12, 16)[index])
            f.setBold(True)
            p.setFont(f)
            p.drawText(QRectF(0, 0, 18, 18), Qt.AlignmentFlag.AlignCenter, "A")
            return
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#f2f2f2"))
        r = (3.0, 5.0, 7.5)[index]
        p.drawEllipse(QPointF(9, 9), r / 2 + 1, r / 2 + 1)
    return _icon(draw)


def size_for(kind: str, index: int) -> float:
    """Logical-pixel size of thin / medium / thick for a tool."""
    if kind == "text":
        return TEXT_SIZES[index]
    if kind == "mosaic":
        return MOSAIC_SIZES[index]
    return SIZES[index]
