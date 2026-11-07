"""Save pictures of the settings window (nothing real is changed).

    python tools_dev/preview_settings.py OUT_DIR
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)
from app import i18n  # noqa: E402
from app.config import Config  # noqa: E402
from app.settings_window import SettingsWindow  # noqa: E402

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
cfg = Config()


class Stand:
    hotkey_ok = True
    def hotkey_text(self): return cfg["hotkey"]
    def default_hotkey(self): return "Ctrl+Alt+A"
    def save_dir(self): return Path(cfg["save_dir"])
    def autostart_enabled(self): return False
    def __getattr__(self, _): return lambda *a, **k: None


for lang in ("en", "zh", "ja"):
    i18n.set_language(lang)
    w = SettingsWindow(Stand())
    w.show()
    QTest.qWait(200)
    w.grab().save(str(out / f"settings_{lang}.png"))
    if lang == "zh":
        w.hotkey_edit.setFocus()
        QTest.qWait(150)
        w.grab().save(str(out / "settings_zh_listening.png"))
    w.close()
print("saved to", out)
