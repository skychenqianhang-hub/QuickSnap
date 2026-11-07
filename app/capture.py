"""Take a frozen picture of every monitor, in real (physical) pixels."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QImage

from . import win32


@dataclass
class MonitorShot:
    monitor: win32.Monitor
    image: QImage  # exactly monitor.width x monitor.height pixels


def grab_all() -> list[MonitorShot]:
    """One copy of the whole desktop, cut into one image per monitor."""
    vx, vy, vw, vh = win32.virtual_screen_rect()
    raw = win32.grab_rect(vx, vy, vw, vh)
    desktop = QImage(raw, vw, vh, vw * 4, QImage.Format.Format_RGB32).copy()  # copy owns memory
    shots = []
    for mon in win32.list_monitors():
        img = desktop.copy(mon.left - vx, mon.top - vy, mon.width, mon.height)
        shots.append(MonitorShot(mon, img))
    return shots
