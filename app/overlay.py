"""The capture screen: dims every monitor, lets the user drag out an area,
then shows a small toolbar (Copy / Save / Save as / Cancel).

One borderless always-on-top window per monitor. Each window shows a frozen
picture of its monitor taken just before it opened, so what you select is
exactly what was on screen when you pressed the hotkey.

Selections are kept in the monitor's real pixels; only drawing converts to
Qt's scaled ("logical") coordinates. That keeps the saved image sharp and
correctly placed at 125% / 150% display scaling.
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, Signal, QObject
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication, QKeySequence, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QToolButton, QWidget

from . import win32
from .capture import MonitorShot
from .i18n import tr

ACCENT = QColor("#2F9BFF")
DIM = QColor(0, 0, 0, 110)
MIN_DRAG = 4  # real pixels; anything smaller counts as a click


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

    def __init__(self, screen, shots: list[MonitorShot]):
        super().__init__(None)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        self.setGeometry(screen.geometry())
        self._shots = shots
        self.shot: MonitorShot | None = None
        self._pix = QPixmap()
        self.sel: QRect | None = None       # real pixels, relative to this monitor
        self._drag_from: QPoint | None = None
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
            self.shot = shot
            self._pix = QPixmap.fromImage(shot.image)
            self.update()

    def showEvent(self, e):
        super().showEvent(e)
        self._match_monitor()  # re-check once Windows has really placed the window

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

    # ---- selection

    def clear_selection(self) -> None:
        self.sel = None
        self._drag_from = None
        self.toolbar.hide()
        self.update()

    def select_all(self) -> None:
        self.sel = QRect(0, 0, self._pix.width(), self._pix.height())
        self._finish_selection()

    def _finish_selection(self) -> None:
        self._drag_from = None
        self._place_toolbar()
        self.toolbar.show()
        self.toolbar.raise_()
        self.update()

    def _place_toolbar(self) -> None:
        if self.sel is None:
            return
        r = self.to_logical(self.sel)
        tb = self.toolbar.sizeHint()
        gap = 6
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

    # ---- mouse and keys

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_from = self.to_real(e.position())
            self.sel = None
            self.toolbar.hide()
            self.selection_started.emit(self)
            self.update()
        elif e.button() == Qt.MouseButton.RightButton:
            if self.sel is not None:
                self.clear_selection()
            else:
                self.action.emit("cancel")

    def mouseMoveEvent(self, e):
        if self._drag_from is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.sel = QRect(self._drag_from, self.to_real(e.position())).normalized()
            # QRect(p1, p2) includes p2; keep width = |dx| so a drag of N px gives N px
            self.sel.setSize(self.sel.size() - QRect(0, 0, 1, 1).size())
            self.update()
        else:
            self.update()  # keeps the hint / crosshair label following the mouse

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton or self._drag_from is None:
            return
        if self.sel is None or (self.sel.width() < MIN_DRAG and self.sel.height() < MIN_DRAG):
            self.select_all()  # a plain click takes the whole screen
        else:
            self._finish_selection()

    def mouseDoubleClickEvent(self, e):
        if (e.button() == Qt.MouseButton.LeftButton and self.sel is not None
                and self.sel.contains(self.to_real(e.position()))):
            self.action.emit("copy")

    def keyPressEvent(self, e):
        k = e.key()
        if k == Qt.Key.Key_Escape:
            self.action.emit("cancel")
        elif k in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.sel is not None:
            self.action.emit("copy")
        elif e.matches(QKeySequence.StandardKey.Copy) and self.sel is not None:
            self.action.emit("copy")
        elif e.matches(QKeySequence.StandardKey.Save) and self.sel is not None:
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
        if self.sel is not None and not self.sel.isEmpty():
            r = self.to_logical(self.sel)
            p.drawPixmap(r, self._pix, QRectF(self.sel))
            pen = QPen(ACCENT, 1.5)
            pen.setCosmetic(True)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(r)
            self._draw_label(p, f"{self.sel.width()} × {self.sel.height()}", r.topLeft())
        elif self._drag_from is None:
            pos = self.mapFromGlobal(QCursor.pos())
            if self.rect().contains(pos):
                self._draw_label(p, tr("Drag to select · Click for the whole screen · Esc to cancel"),
                                 QPointF(pos) + QPointF(14, 22), below=True)

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


class CaptureSession(QObject):
    """Opens one overlay per monitor and reports what the user chose.

    finished(action, image) — action is "copy" / "save" / "save_as" / "cancel";
    image is None when cancelled.
    """

    finished = Signal(str, object)

    def __init__(self, shots: list[MonitorShot]):
        super().__init__()
        self.overlays: list[Overlay] = []
        for screen in QGuiApplication.screens():
            ov = Overlay(screen, shots)
            ov.action.connect(lambda a, o=ov: self._on_action(o, a))
            ov.selection_started.connect(self._on_selection_started)
            self.overlays.append(ov)
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
        for ov in self.overlays:
            ov.close()
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
