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


def installer_choices_path() -> Path:
    return config_dir() / "installer.json"


def take_installer_choices(cfg: "Config") -> dict:
    """The installer (first install only) leaves %APPDATA%\\QuickSnap\\installer.json with
    what the user picked: {"save_dir": ..., "language": ..., "autostart": true/false}.
    Apply folder + language to the settings, delete the file, return what was in it
    (the caller switches auto-start on or off)."""
    path = installer_choices_path()
    try:
        raw = path.read_text(encoding="utf-8-sig")  # Inno Setup writes a UTF-8 BOM
    except OSError:
        return {}
    try:
        path.unlink()  # used once, even if broken
    except OSError:
        pass
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    if isinstance(data.get("save_dir"), str) and data["save_dir"].strip():
        cfg["save_dir"] = data["save_dir"].strip()
    if data.get("language") in ("en", "zh", "ja"):
        cfg["language"] = data["language"]
    return data


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
