"""The capture screen: dims every monitor and lets the user pick what to keep.

    hover          the window under the mouse lights up (empty desktop = whole screen)
    click          take that window / screen
    drag           draw your own box
    after picking  drag the 8 little squares to resize, drag inside to move,
                   arrow keys nudge by 1 pixel (Shift = 10); toolbar: Copy / Save / Save as / Cancel
    drawing        toolbar tools box / circle / arrow / pen / text / mosaic (+ colour and size strip),
                   Ctrl+Z undo; once something is drawn the box is locked (app/annotate.py)

One borderless always-on-top window per monitor. Each shows a frozen picture
of its monitor taken just before it opened, so what you pick is exactly what
was on screen when you pressed the hotkey.

Boxes are kept in the monitor's real pixels; only drawing converts to Qt's
scaled ("logical") coordinates. That keeps the image sharp and correctly
placed at 125% / 150% display scaling.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QObject, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QCursor, QFont, QGuiApplication, QImage, QKeySequence, QPainter, QPen,
                           QPixmap)
from PySide6.QtWidgets import QFrame, QHBoxLayout, QTextEdit, QToolButton, QWidget

from . import annotate
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


_BAR_STYLE = (
    "#snapToolbar, #snapOptions { background: #2b2b2b; border: 1px solid #444; border-radius: 6px; }"
    "QToolButton { color: #f2f2f2; background: transparent; border: 1px solid transparent;"
    " padding: 5px 10px; font-size: 13px; border-radius: 4px; }"
    "QToolButton:hover { background: #3d3d3d; }"
    "QToolButton:checked { background: #1f4f80; border-color: #2F9BFF; }"
    "QToolButton:disabled { color: #777; }"
    "QToolButton#toolBtn, QToolButton#sizeBtn { padding: 5px 7px; }"
    "QToolButton#copyBtn { color: #4cd964; font-weight: bold; }"
    "QToolButton#cancelBtn { color: #ff6b6b; }"
    "QFrame#barSep { background: #4a4a4a; }"
)


def _separator(parent: QWidget) -> QFrame:
    sep = QFrame(parent)
    sep.setObjectName("barSep")
    sep.setFixedSize(1, 20)
    return sep


class Toolbar(QFrame):
    """[box][circle][arrow][pen] [undo] | Save as… Save ✕ Cancel ✓ Copy"""

    action = Signal(str)        # "copy" / "save" / "save_as" / "cancel"
    tool_clicked = Signal(str)  # "rect" / "ellipse" / "arrow" / "pen"
    undo_clicked = Signal()

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("snapToolbar")
        self.setStyleSheet(_BAR_STYLE)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 3, 4, 3)
        lay.setSpacing(2)
        self.tool_buttons: dict[str, QToolButton] = {}
        for kind, tip in [("rect", tr("Box")), ("ellipse", tr("Circle")), ("arrow", tr("Arrow")),
                          ("pen", tr("Pen")), ("text", tr("Text")), ("mosaic", tr("Mosaic"))]:
            b = QToolButton(self)
            b.setObjectName("toolBtn")
            b.setIcon(annotate.tool_icon(kind))
            b.setIconSize(QSize(18, 18))
            b.setCheckable(True)
            b.setToolTip(tip)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=kind: self.tool_clicked.emit(k))
            lay.addWidget(b)
            self.tool_buttons[kind] = b
        self.undo_button = QToolButton(self)
        self.undo_button.setObjectName("toolBtn")
        self.undo_button.setIcon(annotate.tool_icon("undo"))
        self.undo_button.setIconSize(QSize(18, 18))
        self.undo_button.setToolTip(tr("Undo (Ctrl+Z)"))
        self.undo_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.undo_button.setEnabled(False)
        self.undo_button.clicked.connect(self.undo_clicked)
        lay.addWidget(self.undo_button)
        lay.addSpacing(4)
        lay.addWidget(_separator(self))
        lay.addSpacing(4)
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

    def show_tool(self, kind: str | None) -> None:
        for k, b in self.tool_buttons.items():
            b.setChecked(k == kind)


class ToolOptions(QFrame):
    """Line thickness (3 dots) and colour (8 swatches) for the drawing tools."""

    changed = Signal()

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("snapOptions")
        self.setStyleSheet(_BAR_STYLE)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 3, 6, 3)
        lay.setSpacing(2)
        self.size_buttons = []
        for i, tip in enumerate([tr("Thin"), tr("Medium"), tr("Thick")]):
            b = QToolButton(self)
            b.setObjectName("sizeBtn")
            b.setIcon(annotate.size_icon(i))
            b.setIconSize(QSize(18, 18))
            b.setCheckable(True)
            b.setToolTip(tip)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, n=i: self._pick_size(n))
            lay.addWidget(b)
            self.size_buttons.append(b)
        lay.addSpacing(4)
        self._sep = _separator(self)
        lay.addWidget(self._sep)
        lay.addSpacing(6)
        self.color_buttons = []
        for c in annotate.PALETTE:
            b = QToolButton(self)
            b.setCheckable(True)
            b.setFixedSize(20, 20)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(f"QToolButton {{ background: {c}; border: 2px solid #555; border-radius: 3px; padding: 0; }}"
                            f"QToolButton:checked {{ border: 2px solid #ffffff; }}"
                            f"QToolButton:hover {{ border: 2px solid #bbbbbb; }}")
            b.clicked.connect(lambda _=False, col=c: self._pick_color(col))
            lay.addWidget(b)
            self.color_buttons.append((c, b))
        self._kind = "line"
        self.sync()
        self.adjustSize()

    def set_tool(self, tool: str) -> None:
        """Text: sizes are small / medium / large letters. Mosaic: no colours (it has none)."""
        kind = "text" if tool == "text" else ("mosaic" if tool == "mosaic" else "line")
        if kind == self._kind:
            return
        self._kind = kind
        tips = [tr("Small"), tr("Medium"), tr("Large")] if kind == "text" else [tr("Thin"), tr("Medium"), tr("Thick")]
        for i, b in enumerate(self.size_buttons):
            b.setIcon(annotate.size_icon(i, "text" if kind == "text" else "line"))
            b.setToolTip(tips[i])
        show_colors = kind != "mosaic"
        self._sep.setVisible(show_colors)
        for _, b in self.color_buttons:
            b.setVisible(show_colors)
        self.adjustSize()

    def sync(self) -> None:
        """Show the current choice (annotate.prefs) as pressed buttons."""
        for i, b in enumerate(self.size_buttons):
            b.setChecked(i == annotate.prefs["size"])
        for c, b in self.color_buttons:
            b.setChecked(c.upper() == str(annotate.prefs["color"]).upper())

    def _pick_size(self, n: int) -> None:
        annotate.prefs["size"] = n
        self.sync()
        self.changed.emit()

    def _pick_color(self, color: str) -> None:
        annotate.prefs["color"] = color
        self.sync()
        self.changed.emit()


class TextEditor(QTextEdit):
    """Where the user types a text label on the picture. A normal Qt text box, so every
    input method (Chinese pinyin, Japanese ...) works. Enter = done, Shift+Enter = new line,
    Esc = drop this text. Grows with its content; transparent, so it looks like the result."""

    committed = Signal()
    cancelled = Signal()

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setFrameStyle(QFrame.Shape.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.setAcceptRichText(False)
        self.document().setDocumentMargin(0)
        self.setCursor(Qt.CursorShape.IBeamCursor)
        self.textChanged.connect(self._fit)
        self.color = annotate.PALETTE[0]
        self.pixel_size = annotate.TEXT_SIZES[1]   # logical pixels

    def style_as(self, color: str, pixel_size: float) -> None:
        """Colour and font size (logical pixels) — same font as the saved picture uses."""
        self.color = color
        self.pixel_size = pixel_size
        self.setFont(annotate.text_font(pixel_size))
        self.setStyleSheet(f"QTextEdit {{ background: transparent; color: {color}; border: none; }}")
        self._fit()

    def _fit(self) -> None:
        doc = self.document()
        doc.adjustSize()
        size = doc.size()
        fm = self.fontMetrics()
        w = max(size.width(), fm.horizontalAdvance("M") * 2) + fm.horizontalAdvance("M")  # room for the cursor
        h = max(size.height(), fm.height())
        self.setFixedSize(int(math.ceil(w)), int(math.ceil(h)))
        if self.parent() is not None:
            self.parent().update()           # the dashed frame around it

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not e.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.committed.emit()
            return
        if e.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            return
        super().keyPressEvent(e)


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
        self.tool: str | None = None             # drawing tool in use, None = adjusting the box
        self.shapes: list[annotate.Shape] = []   # what has been drawn (real pixels, this monitor)
        self._shape: annotate.Shape | None = None  # the one being drawn right now
        self.toolbar = Toolbar(self)
        self.toolbar.hide()
        self.toolbar.action.connect(self.action)
        self.toolbar.tool_clicked.connect(self.toggle_tool)
        self.toolbar.undo_clicked.connect(self.undo)
        self.options = ToolOptions(self)
        self.options.hide()
        self.options.changed.connect(self._restyle_text)
        self.text_edit = TextEditor(self)
        self.text_edit.hide()
        self.text_edit.committed.connect(self.commit_text)
        self.text_edit.cancelled.connect(self.cancel_text)
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
        self._clear_drawing()
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
        self.options.ensurePolished()
        self.options.grab()
        self.text_edit.style_as(annotate.PALETTE[0], annotate.TEXT_SIZES[1])
        self.text_edit.ensurePolished()
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
        """While hovering, drawing a box or dragging an edge; not while moving, after picking
        or while drawing on the picture."""
        if self.cursor_px is None or self.shot is None:
            return False
        if self._mode in (None, "pending"):
            return self.sel is None
        return self._mode not in ("move", "draw")

    # ---- drawing on the picture

    @property
    def locked(self) -> bool:
        """Once something is drawn the box stays put (moving it would misplace the drawings)."""
        return bool(self.shapes)

    def toggle_tool(self, kind: str) -> None:
        self.set_tool(None if self.tool == kind else kind)

    def set_tool(self, kind: str | None) -> None:
        self.commit_text()
        self.tool = kind
        self.toolbar.show_tool(kind)
        if kind is None:
            self.options.hide()
        else:
            self.options.set_tool(kind)
            self.options.sync()
            self._place_toolbar()
            self.options.show()
            self.options.raise_()
        self.setFocus()  # keep Esc / Enter / Ctrl+Z working after clicking a button
        self.update()

    def undo(self) -> None:
        if self.typing:       # still typing: drop that text first
            self.cancel_text()
            return
        if self.shapes:
            self.shapes.pop()
            self.toolbar.undo_button.setEnabled(bool(self.shapes))
            self.update()

    def _clear_drawing(self) -> None:
        self.shapes = []
        self._shape = None
        self.tool = None
        self.toolbar.show_tool(None)
        self.toolbar.undo_button.setEnabled(False)
        self.options.hide()
        self.text_edit.hide()
        self.text_edit.clear()

    # ---- text labels

    @property
    def typing(self) -> bool:
        """A text box is open (isHidden, not isVisible: also right while the window is off screen)."""
        return not self.text_edit.isHidden()

    def _begin_text(self, pos: QPointF) -> None:
        """Open the text box where the user clicked (the click is the middle of the first line)."""
        self.commit_text()
        px = annotate.TEXT_SIZES[annotate.prefs["size"]]
        self.text_edit.clear()
        self.text_edit.style_as(annotate.prefs["color"], px)
        r = self.to_logical(self.sel)
        h = self.text_edit.fontMetrics().height()
        x = min(max(pos.x(), r.left()), r.right() - 4)
        y = min(max(pos.y() - h / 2, r.top()), r.bottom() - h)
        self.text_edit.move(round(x), round(y))
        self.text_edit.show()
        self.text_edit.raise_()
        self.text_edit.setFocus()
        self.update()

    def commit_text(self) -> None:
        """Turn the text being typed into a label on the picture (empty text is dropped)."""
        ed = self.text_edit
        if not self.typing:
            return
        text = ed.toPlainText().rstrip("\n")
        ed.hide()
        if text.strip():
            sx, sy = self._scale()
            top_left = QPointF(ed.x() * sx, ed.y() * sy)
            self.shapes.append(annotate.Shape("text", ed.color, ed.pixel_size * sx, [top_left], text=text))
            self.toolbar.undo_button.setEnabled(True)
        ed.clear()
        self.setFocus()
        self.update()

    def cancel_text(self) -> None:
        self.text_edit.hide()
        self.text_edit.clear()
        self.setFocus()
        self.update()

    def _restyle_text(self) -> None:
        """Colour / size changed while typing: apply it to the text box right away."""
        if self.typing:
            self.text_edit.style_as(annotate.prefs["color"], annotate.TEXT_SIZES[annotate.prefs["size"]])
            self.text_edit.setFocus()

    def _clamp_to_sel(self, p: QPointF) -> QPointF:
        r = self.sel
        return QPointF(min(max(p.x(), r.left()), r.left() + r.width()),
                       min(max(p.y(), r.top()), r.top() + r.height()))

    def _real_f(self, pos: QPointF) -> QPointF:
        """Mouse position in real pixels, keeping fractions (smooth pen lines)."""
        sx, sy = self._scale()
        return QPointF(pos.x() * sx, pos.y() * sy)

    def _start_shape(self, pos: QPointF) -> None:
        sx, _ = self._scale()
        width = annotate.size_for(self.tool, annotate.prefs["size"]) * sx   # same look on any scaling
        start = self._clamp_to_sel(self._real_f(pos))
        self._shape = annotate.Shape(self.tool, annotate.prefs["color"], width, [start, QPointF(start)])
        if self.tool in ("pen", "mosaic"):
            self._shape.points = [start]
        if self.tool == "mosaic":
            self._shape.cell = annotate.MOSAIC_CELL * sx
        self._mode = "draw"

    def _extend_shape(self, pos: QPointF) -> None:
        p = self._clamp_to_sel(self._real_f(pos))
        if self._shape.kind in ("pen", "mosaic"):
            last = self._shape.points[-1]
            if abs(p.x() - last.x()) + abs(p.y() - last.y()) >= 1.0:
                self._shape.points.append(p)
        else:
            self._shape.points[-1] = p

    def _finish_shape(self) -> None:
        if self._shape is not None and self._shape.is_meaningful():
            self.shapes.append(self._shape)
            self.toolbar.undo_button.setEnabled(True)
        self._shape = None
        self._mode = None

    # ---- selection

    def clear_selection(self) -> None:
        self.sel = None
        self._mode = None
        self._clear_drawing()
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
        # the colour / thickness strip goes on the far side of the toolbar, away from the box
        op = self.options.sizeHint()
        ox = min(max(x, 0), self.width() - op.width())
        toolbar_above_box = y + tb.height() <= r.top()
        oy_below, oy_above = y + tb.height() + 4, y - 4 - op.height()
        if toolbar_above_box:
            oy = oy_above if oy_above >= 0 else oy_below
        else:
            oy = oy_below if oy_below + op.height() <= self.height() else oy_above
        self.options.setGeometry(round(ox), round(min(max(oy, 0), self.height() - op.height())),
                                 op.width(), op.height())

    def cropped(self):
        """The picked area, with the drawings on it, in real pixels."""
        if self.shot is None or self.sel is None or self.sel.isEmpty():
            return None
        self.commit_text()   # text still being typed counts too
        return annotate.render(self.shot.image, self.shapes, self.sel)

    def _part_under(self, pos: QPointF) -> str:
        if self.sel is None or self.locked or self.tool is not None:
            return ""          # drawing / drawn: the box can't be resized or moved
        return geo.hit_test(self.to_logical(self.sel), pos, GRAB_TOL)

    # ---- mouse

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.RightButton:
            if self._mode == "draw":
                return
            if self.tool is not None:                  # first right-click just puts the tool down
                self.set_tool(None)
            elif self.sel is not None or self._mode is not None:
                self.clear_selection()
                self.hover = self.window_at(self.to_real(e.position()))
                self.update()
            else:
                self.action.emit("cancel")
            return
        if e.button() != Qt.MouseButton.LeftButton:
            return
        if self.sel is not None and (self.tool is not None or self.locked):
            inside = self.to_logical(self.sel).contains(e.position())
            if self.tool == "text":
                if inside:
                    self._begin_text(e.position())     # finishes any text being typed, starts a new one
                else:
                    self.commit_text()
            elif self.tool is not None and inside:
                self._start_shape(e.position())
                self.update()
            return                                     # outside the box: keep the drawings, do nothing
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
        if mode == "draw":
            self._extend_shape(e.position())
            self.update()
            return
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
        if mode == "draw":
            self._extend_shape(e.position())
            self._finish_shape()
            self.update()
            return
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
        if self.tool is not None:                      # while drawing a double-click is just two clicks
            self.mousePressEvent(e)
            return
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
            if self.sel is not None:
                if self._mode is None and not self.locked and self.tool is None:  # nudge the box
                    self.sel = geo.move(self.sel, dx, dy, self.bounds())
                    self._place_toolbar()
                    self.update()
            else:                                             # no box yet: nudge the mouse pointer
                cx, cy = win32.cursor_pos()
                win32.set_cursor_pos(cx + dx, cy + dy)
        elif self.sel is not None and e.matches(QKeySequence.StandardKey.Undo):
            if self._mode is None:
                self.undo()
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
            if self.sel is not None and (self.shapes or self._shape is not None):
                self._draw_shapes(p, r)
            if self.sel is not None and self.typing:
                self._draw_text_frame(p)
            self._draw_label(p, f"{box.width()} × {box.height()}", r.topLeft())
            if self.sel is not None and not self.locked and self.tool is None:
                self._draw_handles(p, r)
        if self.sel is None and self._mode in (None, "pending") and self.cursor_px is not None:
            self._draw_banner(p, tr("Click a window or the screen · Drag to select · Esc to cancel"))
        elif self.sel is not None and self._mode is None:
            avoid = [self.to_logical(self.sel), QRectF(self.toolbar.geometry())]
            if self.options.isVisible():
                avoid.append(QRectF(self.options.geometry()))
            if self.tool == "text":
                text = tr("Click inside the box to type · Enter to finish, Shift+Enter for a new line · "
                          "Esc drops the text")
            elif self.tool is not None:
                text = tr("Drag inside the box to draw · Ctrl+Z to undo · "
                          "Right-click or click the tool again to stop drawing")
            elif self.locked:
                text = tr("Enter or double-click to copy · Ctrl+Z to undo · Esc to cancel")
            else:
                text = tr("Drag the squares to resize · Arrow keys to nudge · "
                          "Enter or double-click to copy · Esc to cancel")
            self._draw_banner(p, text, avoid)
        if self.magnifier_visible():
            self._draw_magnifier(p)
        p.end()
        if self._report_paint and self.shot is not None and self.isVisible():
            self._report_paint = False
            self.first_painted.emit()

    def _draw_shapes(self, p: QPainter, sel_logical: QRectF) -> None:
        """Shapes are in real pixels: scale them down to the screen, clipped to the box."""
        sx, sy = self._scale()
        p.save()
        p.setClipRect(sel_logical)
        p.scale(1 / sx, 1 / sy)
        shapes = self.shapes + ([self._shape] if self._shape is not None else [])
        annotate.paint_shapes(p, shapes, self.shot.image if self.shot is not None else None)
        p.restore()

    def _draw_text_frame(self, p: QPainter) -> None:
        """Dashed frame around the text being typed (dark + light, visible on any background)."""
        r = QRectF(self.text_edit.geometry()).adjusted(-4, -2, 4, 2)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(0, 0, 0, 160), 1))
        p.drawRect(r)
        dash = QPen(QColor(255, 255, 255, 230), 1, Qt.PenStyle.DashLine)
        p.setPen(dash)
        p.drawRect(r)

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
