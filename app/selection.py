"""Selection-box geometry, kept free of any window code so it is easy to test.

All rectangles here are QRect in real pixels relative to one monitor.
"Edges" is a string made of the letters l / r / t / b saying which sides a
handle drags: "l" = left edge, "rb" = bottom-right corner, "" = nothing,
"move" = the whole box.
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF


def windows_on_monitor(rects: list[tuple[int, int, int, int]], mon_left: int, mon_top: int,
                       mon_w: int, mon_h: int) -> list[QRect]:
    """Desktop-wide window rectangles -> rectangles on this monitor (clipped), topmost first."""
    screen = QRect(0, 0, mon_w, mon_h)
    out = []
    for (l, t, r, b) in rects:
        q = QRect(l - mon_left, t - mon_top, r - l, b - t).intersected(screen)
        if q.width() > 0 and q.height() > 0:
            out.append(q)
    return out


def window_at(windows: list[QRect], p: QPoint, whole: QRect) -> QRect:
    """The topmost window under the point, or the whole screen if there is none."""
    for w in windows:
        if w.contains(p):
            return QRect(w)
    return QRect(whole)


def from_corners(x1: int, y1: int, x2: int, y2: int) -> QRect:
    """Rectangle between two corner points; width = |x2 - x1| exactly (no +1)."""
    return QRect(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))


def hit_test(r: QRectF, pos: QPointF, tol: float) -> str:
    """Which part of the (on-screen, logical) box is under the mouse."""
    near_l = abs(pos.x() - r.left()) <= tol
    near_r = abs(pos.x() - r.right()) <= tol
    near_t = abs(pos.y() - r.top()) <= tol
    near_b = abs(pos.y() - r.bottom()) <= tol
    in_x = r.left() - tol <= pos.x() <= r.right() + tol
    in_y = r.top() - tol <= pos.y() <= r.bottom() + tol
    if not (in_x and in_y):
        return ""
    edges = ""
    if near_l and not near_r:
        edges += "l"
    elif near_r:
        edges += "r"
    if near_t and not near_b:
        edges += "t"
    elif near_b:
        edges += "b"
    if edges:
        return edges
    return "move" if r.contains(pos) else ""


def resize(orig: QRect, edges: str, p: QPoint, bounds: QRect) -> QRect:
    """Drag the given edges of `orig` to point p (may flip past the opposite edge)."""
    x1, y1 = orig.left(), orig.top()
    x2, y2 = orig.left() + orig.width(), orig.top() + orig.height()  # exclusive right / bottom
    px = min(max(p.x(), bounds.left()), bounds.left() + bounds.width())
    py = min(max(p.y(), bounds.top()), bounds.top() + bounds.height())
    if "l" in edges:
        x1 = px
    if "r" in edges:
        x2 = px
    if "t" in edges:
        y1 = py
    if "b" in edges:
        y2 = py
    return from_corners(x1, y1, x2, y2)


def move(orig: QRect, dx: int, dy: int, bounds: QRect) -> QRect:
    """Shift the box, stopping at the screen edges."""
    x = min(max(orig.x() + dx, bounds.left()), bounds.left() + bounds.width() - orig.width())
    y = min(max(orig.y() + dy, bounds.top()), bounds.top() + bounds.height() - orig.height())
    return QRect(x, y, orig.width(), orig.height())


def panel_position(cursor: QPointF, w: float, h: float, area_w: float, area_h: float,
                   gap: float = 20.0) -> QPointF:
    """Top-left of the magnifier panel: below-right of the mouse; flips to the left
    near the right edge and above near the bottom edge, and never leaves the screen."""
    x = cursor.x() + gap
    y = cursor.y() + gap
    if x + w > area_w:
        x = cursor.x() - gap - w
    if y + h > area_h:
        y = cursor.y() - gap - h
    x = min(max(x, 0.0), max(area_w - w, 0.0))
    y = min(max(y, 0.0), max(area_h - h, 0.0))
    return QPointF(x, y)


def handle_points(r: QRectF) -> dict[str, QPointF]:
    """Centres of the 8 little squares drawn on the box."""
    cx, cy = r.center().x(), r.center().y()
    return {
        "lt": QPointF(r.left(), r.top()), "t": QPointF(cx, r.top()), "rt": QPointF(r.right(), r.top()),
        "l": QPointF(r.left(), cy), "r": QPointF(r.right(), cy),
        "lb": QPointF(r.left(), r.bottom()), "b": QPointF(cx, r.bottom()), "rb": QPointF(r.right(), r.bottom()),
    }
