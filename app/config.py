"""User settings, stored in %APPDATA%\\QuickSnap\\config.json."""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import win32

APP_NAME = "QuickSnap"
DEFAULTS = {
    "language": "en",
    "hotkey": "Ctrl+Alt+A",
    "save_dir": "",  # filled on first run by default_save_dir()
}


def config_dir() -> Path:
    base = os.environ.get("QUICKSNAP_CONFIG_DIR") or os.path.join(
        os.environ.get("APPDATA", str(Path.home())), APP_NAME)
    return Path(base)


def config_path() -> Path:
    return config_dir() / "config.json"


def default_save_dir(drives: list[str] | None = None, system_drive: str | None = None) -> Path:
    """First local hard drive that is not the system drive -> X:\\QuickSnap Screenshots.
    Without one, fall back to Pictures\\QuickSnap on the system drive."""
    if drives is None:
        drives = win32.fixed_drives()
    if system_drive is None:
        system_drive = os.environ.get("SystemDrive", "C:")[:1]
    for letter in drives:
        if letter.upper() != system_drive.upper():
            return Path(f"{letter.upper()}:\\QuickSnap Screenshots")
    return Path.home() / "Pictures" / APP_NAME


class Config:
    def __init__(self, path: Path | None = None):
        self.path = path or config_path()
        self.data = dict(DEFAULTS)
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                self.data.update({k: v for k, v in loaded.items() if k in DEFAULTS})
        except (OSError, json.JSONDecodeError):
            pass
        if not self.data.get("save_dir"):
            self.data["save_dir"] = str(default_save_dir())
            self.save()

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value
        self.save()

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            pass
