"""Ties everything together: tray icon, hotkey, capture sessions, saving."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl
from PySide6.QtGui import QAction, QActionGroup, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QFileDialog, QMenu, QSystemTrayIcon

from . import capture, i18n
from .config import APP_NAME, Config
from .hotkey import HotkeyManager, normalize
from .i18n import tr
from .icon import app_icon
from .overlay import CaptureSession

HOTKEY_CAPTURE = 1


def unique_path(folder: Path, when: datetime | None = None) -> Path:
    """QuickSnap_2026-11-07_13-25-30.png, adding _2, _3 ... if the name is taken."""
    stem = f"{APP_NAME}_{(when or datetime.now()).strftime('%Y-%m-%d_%H-%M-%S')}"
    path = folder / f"{stem}.png"
    n = 2
    while path.exists():
        path = folder / f"{stem}_{n}.png"
        n += 1
    return path


class Controller(QObject):
    def __init__(self, app, config: Config, quiet_start: bool = False):
        super().__init__()
        self.app = app
        self.config = config
        self.session: CaptureSession | None = None
        self._last_saved: Path | None = None

        self.hotkeys = HotkeyManager(app)
        self.hotkeys.triggered.connect(self._on_hotkey)

        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.messageClicked.connect(self._on_message_clicked)
        self._build_menu()
        self.tray.show()

        ok = self._register_hotkey()
        if not ok:
            self.notify(tr("Shortcut unavailable"),
                        tr("{0} is already used by another program. Click the tray icon to take a "
                           "screenshot for now.", self.hotkey_text()))
        elif not quiet_start:
            self.notify(tr("QuickSnap is running"),
                        tr("Press {0} to take a screenshot. QuickSnap stays in the tray "
                           "(bottom-right of the screen).", self.hotkey_text()))

    # ---- hotkey

    def hotkey_text(self) -> str:
        try:
            return normalize(self.config["hotkey"])
        except ValueError:
            return self.config["hotkey"]

    def _register_hotkey(self) -> bool:
        return self.hotkeys.register(HOTKEY_CAPTURE, self.config["hotkey"])

    def _on_hotkey(self, hotkey_id: int) -> None:
        if hotkey_id == HOTKEY_CAPTURE:
            self.start_capture()

    # ---- tray

    def _build_menu(self) -> None:
        menu = QMenu()
        act = menu.addAction(tr("Take screenshot") + f"\t{self.hotkey_text()}")
        act.triggered.connect(lambda: QTimer.singleShot(150, self.start_capture))  # let the menu close
        menu.addAction(tr("Open screenshot folder")).triggered.connect(self.open_folder)
        menu.addSeparator()
        lang_menu = menu.addMenu(tr("Language"))
        group = QActionGroup(lang_menu)
        for code, name in i18n.LANGUAGES.items():
            a = QAction(name, lang_menu, checkable=True)
            a.setChecked(code == i18n.current_language())
            a.triggered.connect(lambda _=False, c=code: self.set_language(c))
            group.addAction(a)
            lang_menu.addAction(a)
        menu.addSeparator()
        menu.addAction(tr("Quit QuickSnap")).triggered.connect(self.quit)
        old = self.tray.contextMenu()
        self.tray.setContextMenu(menu)
        self._menu = menu
        if old is not None:
            old.deleteLater()
        self.tray.setToolTip(f"QuickSnap — {self.hotkey_text()}")

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:  # left click
            QTimer.singleShot(150, self.start_capture)

    def _on_message_clicked(self) -> None:
        if self._last_saved is not None:
            self.reveal(self._last_saved)

    def notify(self, title: str, text: str) -> None:
        self.tray.showMessage(title, text, app_icon(), 4000)

    def set_language(self, code: str) -> None:
        self.config["language"] = i18n.set_language(code)
        self._build_menu()

    # ---- capture

    def start_capture(self) -> None:
        if self.session is not None:
            return
        try:
            shots = capture.grab_all()
        except OSError as exc:
            self.notify(tr("Screenshot failed"), str(exc))
            return
        self.session = CaptureSession(shots)
        self.session.finished.connect(self._on_finished)
        self.session.start()

    def _end_session(self) -> None:
        if self.session is not None:
            self.session.close()
            self.session.deleteLater()
            self.session = None

    def _on_finished(self, action: str, image) -> None:
        if action == "cancel" or image is None:
            self._end_session()
            return
        if action == "save_as":
            self.session.hide()
            folder = self.save_dir()
            path_str, _ = QFileDialog.getSaveFileName(
                None, tr("Save screenshot"), str(unique_path(folder)),
                tr("PNG image (*.png);;JPEG image (*.jpg)"))
            if not path_str:
                self.session.reshow()  # back to the selection
                return
            self.session.mark_done()
            QGuiApplication.clipboard().setImage(image)
            self._end_session()
            self._save(image, Path(path_str))
            return
        QGuiApplication.clipboard().setImage(image)
        self._end_session()
        if action == "save":
            folder = self.save_dir()
            try:
                folder.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
            self._save(image, unique_path(folder))

    def _save(self, image, path: Path) -> None:
        if image.save(str(path)):
            self._last_saved = path
            self.notify(tr("Saved and copied"), tr("{0}\nClick to show it in its folder.", str(path)))
        else:
            self.notify(tr("Could not save"),
                        tr("{0}\nThe screenshot is still on the clipboard.", str(path)))

    # ---- folders

    def save_dir(self) -> Path:
        return Path(self.config["save_dir"])

    def open_folder(self) -> None:
        folder = self.save_dir()
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    @staticmethod
    def reveal(path: Path) -> None:
        import subprocess
        subprocess.Popen(["explorer", "/select,", os.path.normpath(str(path))])

    def quit(self) -> None:
        self._end_session()
        self.hotkeys.unregister_all()
        self.tray.hide()
        self.app.quit()
