"""Start QuickSnap when the user signs in to Windows.

Uses the current user's "Run" list in the registry
(HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run) — the same
place Task Manager's "Startup apps" page shows. No administrator rights needed.

If the user turned QuickSnap off in Task Manager, Windows keeps our Run entry but
marks it disabled under ...\\Explorer\\StartupApproved\\Run. We treat that as "off",
and switching it on again in our settings clears that mark.
"""
from __future__ import annotations

import sys
import winreg
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APPROVED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
NAME = "QuickSnap"


def command() -> str:
    """What Windows should run at sign-in."""
    if getattr(sys, "frozen", False):                       # packaged QuickSnap.exe
        return f'"{sys.executable}" --autostart'
    # running from source (development): pythonw.exe main.py
    pyw = Path(sys.executable).with_name("pythonw.exe")
    main = Path(__file__).resolve().parent.parent / "main.py"
    return f'"{pyw}" "{main}" --autostart'


def _read(key_path: str, name: str):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return None


def registered_command(name: str = NAME) -> str | None:
    value = _read(RUN_KEY, name)
    return value if isinstance(value, str) else None


def disabled_in_task_manager(name: str = NAME) -> bool:
    data = _read(APPROVED_KEY, name)
    # first byte: even (02 / 06) = enabled, odd (03 / 07) = disabled by the user
    return isinstance(data, (bytes, bytearray)) and len(data) > 0 and bool(data[0] & 1)


def is_enabled(name: str = NAME) -> bool:
    return registered_command(name) is not None and not disabled_in_task_manager(name)


def enable(name: str = NAME, cmd: str | None = None) -> None:
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, name, 0, winreg.REG_SZ, cmd or command())
    _clear_approved(name)


def disable(name: str = NAME) -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, name)
    except FileNotFoundError:
        pass
    _clear_approved(name)


def _clear_approved(name: str) -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APPROVED_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, name)
    except FileNotFoundError:
        pass


def refresh_path(name: str = NAME) -> bool:
    """If auto-start is on but points at an old location (the program was moved or
    reinstalled elsewhere), point it at this copy. Only for the packaged exe."""
    if not getattr(sys, "frozen", False):
        return False
    current = registered_command(name)
    if current is not None and current != command() and not disabled_in_task_manager(name):
        enable(name)
        return True
    return False
