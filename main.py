"""QuickSnap entry point.

    QuickSnap.exe                 start in the tray
    QuickSnap.exe --autostart     same, without the "running" bubble (used at Windows sign-in)
    QuickSnap.exe --check FILE    self-check, write results to FILE, exit
"""
from __future__ import annotations

import sys


def main(argv: list[str]) -> int:
    if "--check" in argv:
        i = argv.index("--check")
        out = argv[i + 1] if i + 1 < len(argv) else "quicksnap_check.txt"
        from app import selfcheck
        return selfcheck.run(out)

    from app import win32
    if not win32.claim_single_instance("Local\\QuickSnap-single-instance"):
        # Already running: ask that copy to open its settings window (that's what a
        # double-click on the program usually means). Fall back to a message.
        from app.hotkey import SINK_TITLE, WM_SHOW_SETTINGS
        if "--autostart" in argv or win32.ask_running_copy(SINK_TITLE, WM_SHOW_SETTINGS):
            return 0
        from PySide6.QtWidgets import QApplication, QMessageBox
        from app import i18n
        from app.config import Config
        app = QApplication(argv)
        i18n.set_language(Config()["language"])
        QMessageBox.information(None, "QuickSnap",
                                i18n.tr("QuickSnap is already running — look for its icon in the tray "
                                        "(bottom-right of the screen)."))
        return 0

    from PySide6.QtWidgets import QApplication
    from app import i18n
    from app.config import Config
    from app.controller import Controller
    from app.icon import app_icon

    app = QApplication(argv)
    app.setApplicationName("QuickSnap")
    app.setQuitOnLastWindowClosed(False)  # closing a window never quits; only the tray menu does
    app.setWindowIcon(app_icon())
    config = Config()
    from app.config import take_installer_choices
    choices = take_installer_choices(config)   # first run after a fresh install
    if isinstance(choices.get("autostart"), bool):
        from app import autostart
        try:
            autostart.enable() if choices["autostart"] else autostart.disable()
        except OSError:
            pass
    i18n.set_language(config["language"])
    controller = Controller(app, config, quiet_start="--autostart" in argv)  # noqa: F841 (kept alive)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
