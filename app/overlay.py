"""The capture screen: dims every monitor and lets the user pick what to keep.

    hover          the window under the mouse lights up (empty desktop = whole screen)
    click          take that window / screen
    drag           draw your own box
    after picking  drag the 8 little squares to resize, drag inside to move,
                   arrow keys nudge by 1 pixel (Shift = 10); toolbar: Copy / Save / Save as / Cancel

One borderless always-on-top window per monitor. Each shows a frozen picture
of its monitor taken just before it opened, so what you pick is exactly what
was on screen when you pressed the hotkey.

Boxes are kept in the monitor's real pixels; only drawing converts to Qt's
scaled ("logical") coordinates. That keeps the image sharp and correctly
placed at 125% / 150% display scaling.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QPoint, QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QCursor, QFont, QGuiApplication, QImage, QKeySequence, QPainter, QPen,
                           QPixmap)
from PySide6.QtWidgets import QFrame, QHBoxLayout, QToolButton, QWidget

from . import selection as geo
from . import win32
from .capture import MonitorShot
from .i18n import tr

ACCENT = QColor("#2F9BFF")
DIM = QColor(0, 0, 0, 110)
MIN_DRAG = 4      # real pixels; a smaller movement counts as a click
HANDLE = 7.0      # size of the resize squares (logical pixels)
GRAB_TOL = 6.0    # how close to an edge the mouse must be to grab it

# Magnifier: a block of real pixels around the mouse, each drawn as a CELL x CELL square.
MAG_CELL = 5      # logical pixels per real pixel (5x zoom; the user found 8x too much)
MAG_COLS = 27     # odd, so the mouse pixel sits exactly in the middle (27 x 5 = 135 wide)
MAG_ROWS = 23     # 23 x 5 = 115 tall
MAG_GAP = 20      # distance from the mouse pointer
CROSS = QColor(26, 173, 25, 200)  # green crosshair, like WeChat

_CURSORS = {
    "l": Qt.CursorShape.SizeHorCursor, "r": Qt.CursorShape.SizeHorCursor,
    "t": Qt.CursorShape.SizeVerCursor, "b": Qt.CursorShape.SizeVerCursor,
    "lt": Qt.CursorShape.SizeFDiagCursor, "rb": Qt.CursorShape.SizeFDiagCursor,
    "rt": Qt.CursorShape.SizeBDiagCursor, "lb": Qt.CursorShape.SizeBDiagCursor,
    "move": Qt.CursorShape.SizeAllCursor,
}


class Toolbar(QFrame):
    action = Signal(str)  # "copy" / "save" / "save_as" / "cancel"

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("snapToolbar")
        self.setStyleSheet(
            "#snapToolbar { background: #2b2b2b; border: 1px solid #444; border-radius: 6px; }"
            "QToolButton { color: #f2f2f2; background: transparent; border: none;"
            " padding: 5px 10px; font-size: 13px; border-radius: 4px; }"
            "QToolButton:hover { background: #3d3d3d; }"
            "QToolButton#copyBtn { color: #4cd964; font-weight: bold; }"
            "QToolButton#cancelBtn { color: #ff6b6b; }"
        )
        self.setCursor(Qt.CursorShape.ArrowCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 3, 4, 3)
        lay.setSpacing(2)
        for key, text, tip, name in [
            ("save_as", tr("Save as…"), tr("Choose a folder and file name"), "saveAsBtn"),
            ("save", tr("Save"), tr("Save to the screenshot folder (Ctrl+S)"), "saveBtn"),
            ("cancel", "✕  " + tr("Cancel"), tr("Discard this screenshot (Esc)"), "cancelBtn"),
            ("copy", "✓  " + tr("Copy"), tr("Copy to clipboard (Enter or double-click)"), "copyBtn"),
        ]:
            b = QToolButton(self)
            b.setObjectName(name)
            b.setText(text)
            b.setToolTip(tip)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.action.emit(k))
            lay.addWidget(b)
        self.adjustSize()


class Overlay(QWidget):
    action = Signal(str)
    selection_started = Signal(object)  # self
    first_painted = Signal()            # first drawing after reset() (for the timing log)

    def __init__(self, screen, shots: list[MonitorShot], window_rects=()):
        super().__init__(None)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)
        self._report_paint = True
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setMouseTracking(True)
        self.setGeometry(screen.geometry())
        self._shots = shots
        self._window_rects = list(window_rects)  # desktop-wide, topmost first
        self.windows: list[QRect] = []           # same, on this monitor
        self.shot: MonitorShot | None = None
        self._pix = QPixmap()
        self.sel: QRect | None = None            # the chosen box (real pixels, this monitor)
        self.hover: QRect | None = None          # what a click would take right now
        self._mode: str | None = None            # None / "pending" / "new" / "move" / edges like "rb"
        self._press: QPoint | None = None
        self._orig: QRect | None = None
        self.cursor_px: QPoint | None = None     # real pixel under the mouse (this monitor), None = elsewhere
        self._copied: str | None = None          # "Copied #RRGGBB" feedback text
        self._copied_timer = QTimer(self, singleShot=True, interval=1500)
        self._copied_timer.timeout.connect(self._clear_copied)
        self.toolbar = Toolbar(self)
        self.toolbar.hide()
        self.toolbar.action.connect(self.action)
        self._match_monitor()

    # ---- which frozen picture belongs to this window

    def _match_monitor(self) -> None:
        mon = win32.monitor_of_window(int(self.winId()))
        shot = next((s for s in self._shots if s.monitor.handle == mon.handle), None)
        if shot is None:
            shot = next((s for s in self._shots if (s.monitor.left, s.monitor.top) == (mon.left, mon.top)),
                        None)
        if shot is not None and shot is not self.shot:
            self.set_shot(shot)

    def set_shot(self, shot: MonitorShot) -> None:
        self.shot = shot
        self._pix = QPixmap.fromImage(shot.image)
        m = shot.monitor
        self.windows = geo.windows_on_monitor(self._window_rects, m.left, m.top, m.width, m.height)
        self.update()

    def reset(self, shots: list[MonitorShot], window_rects=()) -> None:
        """Get a reused (pooled) window ready for a new screenshot."""
        self._shots = shots
        self._window_rects = list(window_rects)
        self.windows = []
        self.shot = None
        self._pix = QPixmap()
        self.sel = self.hover = None
        self._mode = None
        self._press = self._orig = None
        self.cursor_px = None
        self._copied = None
        self._copied_timer.stop()
        self.toolbar.hide()
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self._report_paint = True
        self._match_monitor()

    def release(self) -> None:
        """After a screenshot: forget the frozen picture so it doesn't sit in memory."""
        self.reset([], ())

    def warm_up(self) -> None:
        """Load fonts, styles and the toolbar once, off screen (nothing is shown)."""
        self.toolbar.ensurePolished()
        self.toolbar.grab()
        img = QImage(400, 80, QImage.Format.Format_RGB32)
        p = QPainter(img)
        self._draw_label(p, "1920 × 1080", QPointF(10, 40))
        p.end()

    def showEvent(self, e):
        super().showEvent(e)
        self._match_monitor()  # re-check once Windows has really placed the window
        if self.shot is not None and self.sel is None:
            m = self.shot.monitor
            cx, cy = win32.cursor_pos()
            if m.left <= cx < m.right and m.top <= cy < m.bottom:
                self.cursor_px = QPoint(cx - m.left, cy - m.top)
                self.hover = self.window_at(self.cursor_px)

    # ---- coordinate conversion (real pixels <-> Qt logical)

    def _scale(self) -> tuple[float, float]:
        if self._pix.isNull() or self.width() == 0 or self.height() == 0:
            return 1.0, 1.0
        return self._pix.width() / self.width(), self._pix.height() / self.height()

    def to_real(self, p: QPointF) -> QPoint:
        sx, sy = self._scale()
        x = min(max(round(p.x() * sx), 0), self._pix.width())
        y = min(max(round(p.y() * sy), 0), self._pix.height())
        return QPoint(x, y)

    def to_logical(self, r: QRect) -> QRectF:
        sx, sy = self._scale()
        return QRectF(r.x() / sx, r.y() / sy, r.width() / sx, r.height() / sy)

    def bounds(self) -> QRect:
        return QRect(0, 0, self._pix.width(), self._pix.height())

    def window_at(self, p: QPoint) -> QRect:
        return geo.window_at(self.windows, p, self.bounds())

    def pixel_under(self, pos: QPointF) -> QPoint:
        """The real pixel the mouse points at (always inside the picture)."""
        p = self.to_real(pos)
        return QPoint(min(p.x(), self._pix.width() - 1), min(p.y(), self._pix.height() - 1))

    def color_at(self, p: QPoint) -> str:
        if self.shot is None:
            return ""
        return self.shot.image.pixelColor(p).name().upper()  # "#RRGGBB"

    def desktop_pos(self, p: QPoint) -> QPoint:
        """Monitor pixel -> whole-desktop pixel (what Windows calls screen coordinates)."""
        m = self.shot.monitor if self.shot else None
        return QPoint(p.x() + (m.left if m else 0), p.y() + (m.top if m else 0))

    def copy_color(self) -> None:
        if self.cursor_px is None:
            return
        color = self.color_at(self.cursor_px)
        QGuiApplication.clipboard().setText(color)
        self._copied = tr("Copied {0}", color)
        self._copied_timer.start()
        self.update()

    def _clear_copied(self) -> None:
        self._copied = None
        self.update()

    def magnifier_visible(self) -> bool:
        """While hovering, drawing a box or dragging an edge; not while moving or after picking."""
        if self.cursor_px is None or self.shot is None:
            return False
        if self._mode in (None, "pending"):
            return self.sel is None
        return self._mode != "move"

    # ---- selection

    def clear_selection(self) -> None:
        self.sel = None
        self._mode = None
        self.toolbar.hide()
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()

    def select(self, r: QRect) -> None:
        self.sel = QRect(r)
        self._finish_selection()

    def select_all(self) -> None:
        self.select(self.bounds())

    def _finish_selection(self) -> None:
        self._mode = None
        self.hover = None
        self._place_toolbar()
        self.toolbar.show()
        self.toolbar.raise_()
        self.update()

    def _place_toolbar(self) -> None:
        if self.sel is None:
            return
        r = self.to_logical(self.sel)
        tb = self.toolbar.sizeHint()
        gap = HANDLE
        x = r.right() - tb.width()
        y = r.bottom() + gap
        if y + tb.height() > self.height():          # no room below -> above
            y = r.top() - gap - tb.height()
        if y < 0:                                     # no room above either -> inside
            y = r.bottom() - gap - tb.height()
        x = min(max(x, 0), self.width() - tb.width())
        y = min(max(y, 0), self.height() - tb.height())
        self.toolbar.setGeometry(round(x), round(y), tb.width(), tb.height())

    def cropped(self):
        if self.shot is None or self.sel is None or self.sel.isEmpty():
            return None
        return self.shot.image.copy(self.sel)

    def _part_under(self, pos: QPointF) -> str:
        if self.sel is None:
            return ""
        return geo.hit_test(self.to_logical(self.sel), pos, GRAB_TOL)

    # ---- mouse

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.RightButton:
            if self.sel is not None or self._mode is not None:
                self.clear_selection()
                self.hover = self.window_at(self.to_real(e.position()))
                self.update()
            else:
                self.action.emit("cancel")
            return
        if e.button() != Qt.MouseButton.LeftButton:
            return
        p = self.to_real(e.position())
        self._press = p
        part = self._part_under(e.position())
        if part:                                       # grab the existing box
            self._mode = part
            self._orig = QRect(self.sel)
            self.toolbar.hide()
        else:                                          # start over: click or new drag
            self.selection_started.emit(self)
            self.sel = None
            self.toolbar.hide()
            self._mode = "pending"
            self.hover = self.window_at(p)
        self.update()

    def mouseMoveEvent(self, e):
        p = self.to_real(e.position())
        self.cursor_px = self.pixel_under(e.position())
        mode = self._mode
        if mode is None:
            if self.sel is None:
                new_hover = self.window_at(p)
                if new_hover != self.hover:
                    self.hover = new_hover
                self.setCursor(Qt.CursorShape.ArrowCursor)
            else:
                self.setCursor(_CURSORS.get(self._part_under(e.position()), Qt.CursorShape.ArrowCursor))
            self.update()
            return
        if mode == "pending":
            if (p - self._press).manhattanLength() < MIN_DRAG:
                self.update()  # keep the magnifier following the mouse
                return
            self._mode = mode = "new"
            self.hover = None
        if mode == "new":
            self.sel = geo.from_corners(self._press.x(), self._press.y(), p.x(), p.y())
        elif mode == "move":
            d = p - self._press
            self.sel = geo.move(self._orig, d.x(), d.y(), self.bounds())
        else:
            self.sel = geo.resize(self._orig, mode, p, self.bounds())
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton or self._mode is None:
            return
        mode = self._mode
        if mode == "pending":
            self.select(self.window_at(self._press))   # a click takes the window / screen
        elif mode == "new":
            if self.sel is None or self.sel.width() < 2 or self.sel.height() < 2:
                self.select(self.window_at(self._press))
            else:
                self._finish_selection()
        else:                                          # finished moving / resizing
            if self.sel is None or self.sel.width() < 1 or self.sel.height() < 1:
                self.sel = self._orig
            self._finish_selection()
        self.setCursor(_CURSORS.get(self._part_under(e.position()), Qt.CursorShape.ArrowCursor))

    def mouseDoubleClickEvent(self, e):
        if (e.button() == Qt.MouseButton.LeftButton and self.sel is not None
                and self.sel.contains(self.to_real(e.position()))):
            self.action.emit("copy")
        else:
            self.mousePressEvent(e)

    def leaveEvent(self, e):
        self.cursor_px = None  # the mouse went to another monitor
        if self._mode is None and self.sel is None:
            self.hover = None
        self.update()
        super().leaveEvent(e)

    # ---- keys

    def keyPressEvent(self, e):
        k = e.key()
        arrows = (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down)
        if k == Qt.Key.Key_Escape:
            self.action.emit("cancel")
        elif k in arrows:
            step = 10 if e.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
            dx = {Qt.Key.Key_Left: -step, Qt.Key.Key_Right: step}.get(k, 0)
            dy = {Qt.Key.Key_Up: -step, Qt.Key.Key_Down: step}.get(k, 0)
            if self.sel is not None and self._mode is None:   # a box is picked: nudge the box
                self.sel = geo.move(self.sel, dx, dy, self.bounds())
                self._place_toolbar()
                self.update()
            else:                                             # otherwise nudge the mouse pointer
                cx, cy = win32.cursor_pos()
                win32.set_cursor_pos(cx + dx, cy + dy)
        elif self.sel is None:
            if e.matches(QKeySequence.StandardKey.Copy):
                self.copy_color()
            else:
                super().keyPressEvent(e)
        elif self._mode not in (None, "pending"):
            super().keyPressEvent(e)                          # mid-drag: ignore Enter / Ctrl+C
        elif k in (Qt.Key.Key_Return, Qt.Key.Key_Enter) or e.matches(QKeySequence.StandardKey.Copy):
            self.action.emit("copy")
        elif e.matches(QKeySequence.StandardKey.Save):
            self.action.emit("save")
        else:
            super().keyPressEvent(e)

    # ---- drawing

    def paintEvent(self, _e):
        p = QPainter(self)
        full = QRectF(self.rect())
        if not self._pix.isNull():
            p.drawPixmap(full, self._pix, QRectF(self._pix.rect()))
        p.fillRect(full, DIM)
        box = self.sel if self.sel is not None else (self.hover if self._mode in (None, "pending") else None)
        if box is not None and not box.isEmpty():
            r = self.to_logical(box)
            p.drawPixmap(r, self._pix, QRectF(box))
            pen = QPen(ACCENT, 2.0 if self.sel is None else 1.5)
            pen.setCosmetic(True)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            # keep the border visible when the box is the whole screen
            p.drawRect(r.adjusted(1, 1, -1, -1) if box == self.bounds() else r)
            self._draw_label(p, f"{box.width()} × {box.height()}", r.topLeft())
            if self.sel is not None:
                self._draw_handles(p, r)
        if self.sel is None and self._mode in (None, "pending") and self.cursor_px is not None:
            self._draw_banner(p, tr("Click a window or the screen · Drag to select · Esc to cancel"))
        elif self.sel is not None and self._mode is None:
            self._draw_banner(p, tr("Drag the squares to resize · Arrow keys to nudge · "
                                    "Enter or double-click to copy · Esc to cancel"),
                              [self.to_logical(self.sel), QRectF(self.toolbar.geometry())])
        if self.magnifier_visible():
            self._draw_magnifier(p)
        p.end()
        if self._report_paint and self.shot is not None and self.isVisible():
            self._report_paint = False
            self.first_painted.emit()

    def _cursor_logical(self) -> QPointF:
        sx, sy = self._scale()
        return QPointF(self.cursor_px.x() / sx, self.cursor_px.y() / sy)

    def _draw_banner(self, p: QPainter, text: str, avoid: list[QRectF] | None = None) -> None:
        """Hint at the top centre of the screen. Moves to the bottom when the top spot would
        cover the mouse, the picked box or the toolbar (stays on top if both spots are taken)."""
        f = QFont(self.font())
        f.setPointSizeF(9.5)
        p.setFont(f)
        fm = p.fontMetrics()
        w, h = fm.horizontalAdvance(text) + 20, fm.height() + 10
        avoid = list(avoid or [])
        if self.cursor_px is not None:
            c = self._cursor_logical()
            avoid.append(QRectF(c.x() - 150, c.y() - 60, 300, 120))
        top_box = QRectF((self.width() - w) / 2, 14, w, h)
        bottom_box = QRectF((self.width() - w) / 2, self.height() - h - 14, w, h)
        box = top_box
        if any(top_box.intersects(a) for a in avoid) and not any(bottom_box.intersects(a) for a in avoid):
            box = bottom_box
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 170))
        p.drawRoundedRect(box, 4, 4)
        p.setPen(QColor("#ffffff"))
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, text)

    def _draw_magnifier(self, p: QPainter) -> None:
        """WeChat-style magnifier: enlarged pixels around the mouse with a green crosshair,
        plus position / colour of the pixel under the mouse."""
        c = self.cursor_px
        color = self.color_at(c)
        pos = self.desktop_pos(c)

        f = QFont(self.font())
        f.setPointSizeF(9)
        p.setFont(f)
        fm = p.fontMetrics()
        rows_txt = [(tr("Position"), f"{pos.x()}, {pos.y()}"), (tr("Color"), color)]
        hints: list[str] = []
        if self.sel is None:  # before a box is picked: arrows move the mouse, Ctrl+C copies the colour
            hints = [tr("Arrow keys: nudge the mouse"), self._copied or tr("Ctrl+C: copy color")]
        pad, line_h, swatch = 8, fm.height() + 3, fm.height() - 4
        label_w = max(fm.horizontalAdvance(a) for a, _ in rows_txt)
        value_w = max(fm.horizontalAdvance(b) for _, b in rows_txt) + swatch + 6
        need_w = max([label_w + 16 + value_w] + [fm.horizontalAdvance(h) for h in hints]) + 2 * pad

        cols = MAG_COLS
        while cols * MAG_CELL < need_w:
            cols += 2                       # stay odd so the mouse pixel is the middle one
        rows = MAG_ROWS
        mag_w, mag_h = cols * MAG_CELL, rows * MAG_CELL
        info_h = 2 * pad + line_h * (len(rows_txt) + len(hints))
        panel_w, panel_h = mag_w, mag_h + info_h

        tl = geo.panel_position(self._cursor_logical(), panel_w + 2, panel_h + 2,
                                self.width(), self.height(), MAG_GAP)
        x, y = round(tl.x()) + 1, round(tl.y()) + 1   # +1: room for the outer border

        # enlarged pixels (nearest neighbour, so every real pixel is a crisp square)
        src = self.shot.image.copy(c.x() - cols // 2, c.y() - rows // 2, cols, rows)  # outside = black
        mag = QRectF(x, y, mag_w, mag_h)
        p.save()
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.drawImage(mag, src)

        # crosshair: lines up to the middle square, and a frame just outside the mouse pixel
        # (outside, so the 5 x 5 square itself stays fully visible)
        cell = QRectF(x + (cols // 2) * MAG_CELL, y + (rows // 2) * MAG_CELL, MAG_CELL, MAG_CELL)
        frame = cell.adjusted(-1, -1, 1, 1)
        mx, my = cell.center().x(), cell.center().y()
        p.setPen(QPen(CROSS, 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(mag.left(), my), QPointF(frame.left(), my))
        p.drawLine(QPointF(frame.right(), my), QPointF(mag.right(), my))
        p.drawLine(QPointF(mx, mag.top()), QPointF(mx, frame.top()))
        p.drawLine(QPointF(mx, frame.bottom()), QPointF(mx, mag.bottom()))
        p.setPen(QPen(CROSS, 1))
        p.drawRect(frame)

        # two-tone border (dark outside, light inside) so it shows on white and on black
        p.setPen(QPen(QColor(255, 255, 255, 230), 1))
        p.drawRect(mag.adjusted(0.5, 0.5, -0.5, -0.5))
        p.setPen(QPen(QColor(0, 0, 0, 200), 1))
        p.drawRect(QRectF(x, y, panel_w, panel_h).adjusted(-0.5, -0.5, 0.5, 0.5))

        # info box under the magnifier
        info = QRectF(x, y + mag_h, panel_w, info_h)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(20, 20, 20, 225))
        p.drawRect(info)
        ty = info.top() + pad
        for i, (label, value) in enumerate(rows_txt):
            line = QRectF(info.left() + pad, ty, panel_w - 2 * pad, line_h)
            p.setPen(QColor("#d0d0d0"))
            p.drawText(line, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)
            p.setPen(QColor("#ffffff"))
            p.drawText(line, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, value)
            if i == 1:  # little colour square in front of #RRGGBB
                sw = QRectF(line.right() - fm.horizontalAdvance(value) - 6 - swatch,
                            line.center().y() - swatch / 2, swatch, swatch)
                p.setPen(QPen(QColor("#ffffff"), 1))
                p.setBrush(QColor(color))
                p.drawRect(sw)
                p.setBrush(Qt.BrushStyle.NoBrush)
            ty += line_h
        for h in hints:
            p.setPen(QColor("#7fd67f") if h == self._copied else QColor("#9a9a9a"))
            p.drawText(QRectF(info.left() + pad, ty, panel_w - 2 * pad, line_h),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, h)
            ty += line_h
        p.restore()

    def _draw_handles(self, p: QPainter, r: QRectF) -> None:
        p.setPen(QPen(QColor("#ffffff"), 1))
        p.setBrush(ACCENT)
        h = HANDLE
        for c in geo.handle_points(r).values():
            sq = QRectF(c.x() - h / 2, c.y() - h / 2, h, h)
            # keep squares on screen when the box touches an edge
            sq.moveLeft(min(max(sq.left(), 0), self.width() - h))
            sq.moveTop(min(max(sq.top(), 0), self.height() - h))
            p.drawRect(sq)

    def _draw_label(self, p: QPainter, text: str, anchor: QPointF, below: bool = False) -> None:
        f = QFont(self.font())
        f.setPointSizeF(9.5)
        p.setFont(f)
        fm = p.fontMetrics()
        w, h = fm.horizontalAdvance(text) + 12, fm.height() + 6
        x = anchor.x()
        y = anchor.y() if below else anchor.y() - h - 4
        if y < 0:
            y = anchor.y() + 4
        x = min(max(x, 0), self.width() - w)
        y = min(max(y, 0), self.height() - h)
        box = QRectF(x, y, w, h)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 180))
        p.drawRoundedRect(box, 3, 3)
        p.setPen(QColor("#ffffff"))
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, text)


class OverlayPool:
    """The capture windows, built once (at start-up) and reused for every screenshot.

    Building them is the slow part (about half a second the first time, mostly loading
    fonts and styles), so doing it ahead keeps the hotkey snappy. They stay hidden and
    hold no picture between screenshots. Rebuilt when monitors or scaling change, or
    when the interface language changes (toolbar texts).
    """

    def __init__(self):
        self.overlays: list[Overlay] = []
        self._key = None
        self.rebuild()

    @staticmethod
    def _screens_key():
        return tuple((s.name(), s.geometry().getRect(), round(s.devicePixelRatio(), 3))
                     for s in QGuiApplication.screens())

    def rebuild(self) -> None:
        for ov in self.overlays:
            ov.close()
            ov.deleteLater()
        self.overlays = [Overlay(screen, []) for screen in QGuiApplication.screens()]
        self._key = self._screens_key()
        for ov in self.overlays:
            ov.warm_up()

    def ensure_current(self) -> None:
        """Monitors plugged in / out or scaling changed since last time -> rebuild."""
        if self._screens_key() != self._key:
            self.rebuild()

    def close(self) -> None:
        for ov in self.overlays:
            ov.close()
            ov.deleteLater()
        self.overlays = []


class CaptureSession(QObject):
    """Shows one overlay per monitor and reports what the user chose.

    finished(action, image) — action is "copy" / "save" / "save_as" / "cancel";
    image is None when cancelled.
    With a pool, its ready-made windows are reused (and only hidden afterwards);
    without one, fresh windows are built (tests, self-check).
    """

    finished = Signal(str, object)
    first_painted = Signal()

    def __init__(self, shots: list[MonitorShot], window_rects=(), pool: OverlayPool | None = None):
        super().__init__()
        self._pool = pool
        if pool is not None:
            pool.ensure_current()
            self.overlays = list(pool.overlays)
            for ov in self.overlays:
                ov.reset(shots, window_rects)
        else:
            self.overlays = [Overlay(screen, shots, window_rects) for screen in QGuiApplication.screens()]
        self._slots = []
        for ov in self.overlays:
            on_action = (lambda a, o=ov: self._on_action(o, a))
            ov.action.connect(on_action)
            ov.selection_started.connect(self._on_selection_started)
            ov.first_painted.connect(self.first_painted)
            self._slots.append((ov, on_action))
        self._done = False

    def start(self) -> None:
        for ov in self.overlays:
            ov.show()
        under = QGuiApplication.screenAt(QCursor.pos())
        target = next((o for o in self.overlays if under and o.geometry() == under.geometry()),
                      self.overlays[0] if self.overlays else None)
        if target is not None:
            target.raise_()
            target.activateWindow()
            target.setFocus()

    def hide(self) -> None:
        for ov in self.overlays:
            ov.hide()

    def reshow(self) -> None:
        self.start()

    def close(self) -> None:
        for ov, on_action in self._slots:
            try:
                ov.action.disconnect(on_action)
                ov.selection_started.disconnect(self._on_selection_started)
                ov.first_painted.disconnect(self.first_painted)
            except (RuntimeError, TypeError):
                pass
        self._slots = []
        for ov in self.overlays:
            if self._pool is not None:
                ov.hide()
                ov.release()          # keep the window, drop the picture
            else:
                ov.close()
                ov.deleteLater()
        self.overlays = []

    def _on_selection_started(self, who: Overlay) -> None:
        for ov in self.overlays:
            if ov is not who:
                ov.clear_selection()
        who.activateWindow()
        who.setFocus()

    def _on_action(self, ov: Overlay, action: str) -> None:
        if self._done:
            return
        if action == "cancel":
            self._done = True
            self.finished.emit("cancel", None)
            return
        img = ov.cropped()
        if img is None:
            return
        if action != "save_as":
            self._done = True
        self.finished.emit(action, img)

    def mark_done(self) -> None:
        self._done = True
