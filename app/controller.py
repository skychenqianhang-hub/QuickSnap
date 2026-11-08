"""Ties everything together: tray icon, hotkey, capture sessions, saving."""
from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl
from PySide6.QtGui import QAction, QActionGroup, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QFileDialog, QMenu, QSystemTrayIcon

from . import annotate, autostart, capture, i18n, timing, win32
from .config import APP_NAME, DEFAULTS, Config
from .hotkey import HotkeyManager, normalize
from .i18n import tr
from .icon import app_icon
from .overlay import CaptureSession, OverlayPool

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
        self.pool: OverlayPool | None = None   # ready-made capture windows (built right after start-up)
        self._last_capture: float | None = None
        self.settings = None  # the settings window while it is open
        self._last_saved: Path | None = None
        self._hotkey_paused = False

        self.hotkeys = HotkeyManager(app)
        self.hotkeys.triggered.connect(self._on_hotkey)
        self.hotkeys.show_requested.connect(self.open_settings)  # QuickSnap.exe started again
        self.hotkeys.quit_requested.connect(self.quit)           # installer / uninstaller is running

        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.messageClicked.connect(self._on_message_clicked)
        self._build_menu()
        self.tray.show()
        QTimer.singleShot(0, self._build_pool)  # right after start-up, once the tray icon is up

        try:
            autostart.refresh_path()  # the program was moved: keep auto-start pointing at this copy
        except OSError:
            pass

        self._load_draw_prefs()
        self.hotkey_ok = self._register_hotkey()
        if not self.hotkey_ok:
            self.notify(tr("Shortcut unavailable"),
                        tr("{0} is already used by another program. Choose another one in Settings "
                           "(right-click the tray icon), or click the tray icon to take a screenshot.",
                           self.hotkey_text()))
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

    @staticmethod
    def default_hotkey() -> str:
        return DEFAULTS["hotkey"]

    def _register_hotkey(self) -> bool:
        return self.hotkeys.register(HOTKEY_CAPTURE, self.config["hotkey"])

    def _on_hotkey(self, hotkey_id: int) -> None:
        if hotkey_id == HOTKEY_CAPTURE:
            self.start_capture("hotkey")

    def pause_hotkey(self) -> None:
        """While the settings window listens for a new combination, the old one must not fire."""
        self.hotkeys.unregister(HOTKEY_CAPTURE)
        self._hotkey_paused = True

    def resume_hotkey(self) -> None:
        if self._hotkey_paused:
            self._hotkey_paused = False
            self.hotkey_ok = self._register_hotkey()

    def set_hotkey(self, text: str) -> str | None:
        """Switch to a new shortcut. Returns an error message, or None when it worked.
        On failure the previous shortcut stays in use."""
        try:
            new = normalize(text)
        except ValueError:
            self.resume_hotkey()
            return tr("This key can't be used. Try a letter, a number or F1–F12.")
        self.hotkeys.unregister(HOTKEY_CAPTURE)
        self._hotkey_paused = False
        if self.hotkeys.register(HOTKEY_CAPTURE, new):
            self.config["hotkey"] = new
            self.hotkey_ok = True
            self._build_menu()
            return None
        self.hotkey_ok = self._register_hotkey()  # put the old one back
        return tr("{0} is already used by another program or by Windows. Choose another one.", new)

    # ---- other settings

    def set_save_dir(self, path: str) -> str | None:
        folder = Path(path)
        try:
            folder.mkdir(parents=True, exist_ok=True)
            probe = folder / ".quicksnap_write_test"
            probe.write_bytes(b"")
            probe.unlink()
        except OSError:
            return tr("Can't save files in this folder. Choose another one.")
        self.config["save_dir"] = str(folder)
        return None

    @staticmethod
    def autostart_enabled() -> bool:
        try:
            return autostart.is_enabled()
        except OSError:
            return False

    def set_autostart(self, on: bool) -> str | None:
        try:
            autostart.enable() if on else autostart.disable()
        except OSError as exc:
            return tr("Windows did not allow the change: {0}", exc.strerror or str(exc))
        return None

    def open_settings(self) -> None:
        from .settings_window import SettingsWindow
        if self.settings is None:
            self.settings = SettingsWindow(self)
            self.settings.closed.connect(self._settings_closed)
        self.settings.show()
        self.settings.raise_()
        self.settings.activateWindow()

    def _settings_closed(self) -> None:
        self.settings = None

    # ---- tray

    def _build_menu(self) -> None:
        menu = QMenu()
        act = menu.addAction(tr("Take screenshot") + f"\t{self.hotkey_text()}")
        act.triggered.connect(lambda: QTimer.singleShot(150, self.start_capture))  # let the menu close
        menu.addAction(tr("Settings…")).triggered.connect(self.open_settings)
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
        if self.pool is not None and self.session is None:
            self._build_pool()  # toolbar texts are baked into the ready-made windows
        if self.settings is not None:  # rebuild the open settings window in the new language
            pos = self.settings.pos()
            old = self.settings
            self.settings = None
            old.closed.disconnect(self._settings_closed)
            old.close()
            self.open_settings()
            self.settings.move(pos)

    # ---- capture

    def _build_pool(self) -> None:
        """Build the capture windows ahead of time (right after start-up, and after a
        language change), so pressing the hotkey only has to show them."""
        t0 = time.perf_counter()
        if self.pool is None:
            self.pool = OverlayPool()
        else:
            self.pool.rebuild()
        timing.write_line(f"start-up | capture windows ready in {(time.perf_counter() - t0) * 1000:.0f} ms")

    def start_capture(self, source: str = "tray") -> None:
        if self.session is not None:
            return
        now = time.monotonic()
        timer = timing.CaptureTimer(
            source, self.hotkeys.last_delay_ms if source == "hotkey" else None,
            None if self._last_capture is None else now - self._last_capture, self._last_capture is None)
        self._last_capture = now
        try:
            windows = win32.list_windows(exclude_pid=os.getpid())
            timer.mark("find windows")
            shots = capture.grab_all()
            timer.mark("screen copy")
        except OSError as exc:
            self.notify(tr("Screenshot failed"), str(exc))
            return
        if self.pool is None:                      # hotkey pressed before the start-up build finished
            self.pool = OverlayPool()
            timer.mark("build windows")
        self.session = CaptureSession(shots, windows, pool=self.pool)
        timer.mark("prepare")
        self.session.finished.connect(self._on_finished)
        self.session.first_painted.connect(timer.finish)
        self.session.start()
        timer.mark("show")

    def _end_session(self) -> None:
        if self.session is not None:
            self.session.close()
            self.session.deleteLater()
            self.session = None
        self._save_draw_prefs()

    def _load_draw_prefs(self) -> None:
        color = str(self.config["draw_color"]).upper()
        size = self.config["draw_size"]
        annotate.prefs["color"] = color if color in annotate.PALETTE else annotate.PALETTE[0]
        annotate.prefs["size"] = size if size in (0, 1, 2) else 1

    def _save_draw_prefs(self) -> None:
        """Remember the colour / thickness used last time (only writes when they changed)."""
        if self.config["draw_color"] != annotate.prefs["color"]:
            self.config["draw_color"] = annotate.prefs["color"]
        if self.config["draw_size"] != annotate.prefs["size"]:
            self.config["draw_size"] = annotate.prefs["size"]

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
        if self.settings is not None:
            self.settings.close()
        self._end_session()
        if self.pool is not None:
            self.pool.close()
        self.hotkeys.close()
        self.tray.hide()
        self.app.quit()
