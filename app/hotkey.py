"""Global hotkeys: text like "Ctrl+Alt+A" <-> Windows RegisterHotKey.

A hidden helper window owns the hotkeys; Windows sends it WM_HOTKEY when the
combination is pressed anywhere, even while QuickSnap is in the background.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal
from PySide6.QtWidgets import QWidget

from . import win32

_MODS = {"CTRL": win32.MOD_CONTROL, "CONTROL": win32.MOD_CONTROL, "ALT": win32.MOD_ALT,
         "SHIFT": win32.MOD_SHIFT, "WIN": win32.MOD_WIN}
_MOD_ORDER = [("Ctrl", win32.MOD_CONTROL), ("Alt", win32.MOD_ALT),
              ("Shift", win32.MOD_SHIFT), ("Win", win32.MOD_WIN)]

_KEYS: dict[str, int] = {}
for _c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789":
    _KEYS[_c] = ord(_c)
for _i in range(1, 25):
    _KEYS[f"F{_i}"] = 0x6F + _i
_KEYS.update({"PRINTSCREEN": 0x2C, "PRTSC": 0x2C, "SPACE": 0x20, "INSERT": 0x2D, "DELETE": 0x2E,
              "HOME": 0x24, "END": 0x23, "PAGEUP": 0x21, "PAGEDOWN": 0x22, "PAUSE": 0x13,
              "`": 0xC0, "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD, ";": 0xBA, "'": 0xDE,
              ",": 0xBC, ".": 0xBE, "/": 0xBF, "\\": 0xDC})
_KEY_NAMES = {"PRTSC": "PrintScreen", "PRINTSCREEN": "PrintScreen", "SPACE": "Space",
              "INSERT": "Insert", "DELETE": "Delete", "HOME": "Home", "END": "End",
              "PAGEUP": "PageUp", "PAGEDOWN": "PageDown", "PAUSE": "Pause"}


def parse(text: str) -> tuple[int, int]:
    """'Ctrl+Alt+A' -> (modifiers, virtual key). Raises ValueError if invalid."""
    parts = [p.strip() for p in text.replace(" ", "").split("+")]
    # allow a literal '+' key? not supported; '=' covers the same physical key
    if not parts or any(not p for p in parts):
        raise ValueError(f"bad hotkey: {text!r}")
    mods, key = 0, None
    for p in parts:
        up = p.upper()
        if up in _MODS:
            mods |= _MODS[up]
        elif key is None and up in _KEYS:
            key = _KEYS[up]
        else:
            raise ValueError(f"bad hotkey: {text!r}")
    if key is None:
        raise ValueError(f"hotkey needs a non-modifier key: {text!r}")
    return mods, key


def normalize(text: str) -> str:
    """Canonical spelling, e.g. 'alt+ctrl+a' -> 'Ctrl+Alt+A'."""
    mods, vk = parse(text)
    names = [n for n, m in _MOD_ORDER if mods & m]
    key = next(k for k, v in _KEYS.items() if v == vk and k not in ("PRTSC",))
    names.append(_KEY_NAMES.get(key, key))
    return "+".join(names)


class _Filter(QAbstractNativeEventFilter):
    def __init__(self, owner: "HotkeyManager"):
        super().__init__()
        self._owner = owner

    def nativeEventFilter(self, event_type, message):
        if event_type == b"windows_generic_MSG" or event_type == "windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == win32.WM_HOTKEY and msg.hWnd == self._owner.hwnd:
                self._owner.triggered.emit(int(msg.wParam))
                return True, 0
        return False, 0


class HotkeyManager(QObject):
    """Registers hotkeys by id; emits triggered(id) when one is pressed."""

    triggered = Signal(int)

    def __init__(self, app):
        super().__init__()
        self._window = QWidget()  # never shown; only its native handle is used
        self._window.setWindowTitle("QuickSnap hotkey sink")
        self.hwnd = int(self._window.winId())
        self._filter = _Filter(self)
        app.installNativeEventFilter(self._filter)
        self._registered: set[int] = set()

    def register(self, hotkey_id: int, text: str) -> bool:
        """Returns False if the text is invalid or another program already owns the combo."""
        self.unregister(hotkey_id)
        try:
            mods, vk = parse(text)
        except ValueError:
            return False
        ok = win32.register_hotkey(self.hwnd, hotkey_id, mods, vk)
        if ok:
            self._registered.add(hotkey_id)
        return ok

    def unregister(self, hotkey_id: int) -> None:
        if hotkey_id in self._registered:
            win32.unregister_hotkey(self.hwnd, hotkey_id)
            self._registered.discard(hotkey_id)

    def unregister_all(self) -> None:
        for hid in list(self._registered):
            self.unregister(hid)
