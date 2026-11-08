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
from .i18n import tr_noop

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


def key_name(vk: int) -> str | None:
    """Display name of a supported key, e.g. 0x41 -> 'A', 0x2C -> 'PrintScreen'."""
    key = next((k for k, v in _KEYS.items() if v == vk and k != "PRTSC"), None)
    return None if key is None else _KEY_NAMES.get(key, key)


def text_from(mods: int, vk: int) -> str | None:
    """(modifiers, virtual key) -> 'Ctrl+Alt+A'; None if the key is not supported."""
    key = key_name(vk)
    if key is None:
        return None
    return "+".join([n for n, m in _MOD_ORDER if mods & m] + [key])


def normalize(text: str) -> str:
    """Canonical spelling, e.g. 'alt+ctrl+a' -> 'Ctrl+Alt+A'."""
    mods, vk = parse(text)
    return text_from(mods, vk)


# Keys that are fine as a shortcut on their own (nobody types them in normal text).
_SOLO_OK = {0x2C, 0x13} | {0x6F + i for i in range(1, 25)}  # PrintScreen, Pause, F1..F24


def problem_with(mods: int, vk: int) -> str | None:
    """Why this combination can't be the screenshot shortcut (English text for tr()),
    or None if it is acceptable. Does not check other programs — RegisterHotKey does that."""
    if key_name(vk) is None:
        return tr_noop("This key can't be used. Try a letter, a number or F1–F12.")
    if vk in _SOLO_OK:
        return None
    if not mods & (win32.MOD_CONTROL | win32.MOD_ALT | win32.MOD_WIN):
        # a bare letter (or Shift+letter) would fire while typing
        return tr_noop("Add Ctrl, Alt or Win, otherwise it would fire while you type.")
    return None


# Qt key -> Windows virtual key, for when Qt doesn't report the native key (tests, some layouts).
def vk_from_qt(qt_key: int) -> int:
    from PySide6.QtCore import Qt
    if 0x30 <= qt_key <= 0x39 or 0x41 <= qt_key <= 0x5A:   # 0-9, A-Z share their codes
        return qt_key
    f1 = int(Qt.Key.Key_F1.value)
    if f1 <= qt_key <= f1 + 23:
        return 0x70 + (qt_key - f1)
    table = {Qt.Key.Key_Print: 0x2C, Qt.Key.Key_Pause: 0x13, Qt.Key.Key_Space: 0x20,
             Qt.Key.Key_Insert: 0x2D, Qt.Key.Key_Delete: 0x2E, Qt.Key.Key_Home: 0x24,
             Qt.Key.Key_End: 0x23, Qt.Key.Key_PageUp: 0x21, Qt.Key.Key_PageDown: 0x22}
    return next((v for k, v in table.items() if int(k.value) == qt_key), 0)


MODIFIER_VKS = {0x10, 0x11, 0x12, 0x5B, 0x5C, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5}  # Shift/Ctrl/Alt/Win


_kernel32 = ctypes.WinDLL("kernel32")
_kernel32.GetTickCount.restype = wintypes.DWORD


class _Filter(QAbstractNativeEventFilter):
    """Looks at every Windows message the program receives and picks out ours.
    Keeps only plain values (the window handle) plus the two signals, so it can
    never fail on a half-deleted owner; any unexpected error just lets the message pass."""

    def __init__(self, hwnd: int, on_hotkey, on_show, on_quit):
        super().__init__()
        self.hwnd = hwnd
        self.on_hotkey = on_hotkey
        self.on_show = on_show
        self.on_quit = on_quit
        self.active = True
        self.last_delay_ms: int | None = None  # key press -> message reached us (for the timing log)

    def nativeEventFilter(self, event_type, message):
        try:
            if not self.active or event_type not in (b"windows_generic_MSG", "windows_generic_MSG"):
                return False, 0
            msg = wintypes.MSG.from_address(int(message))
            if msg.hWnd == self.hwnd:
                if msg.message == win32.WM_HOTKEY:
                    # msg.time = when Windows posted it (ms since boot, wraps after 49 days)
                    self.last_delay_ms = (_kernel32.GetTickCount() - msg.time) & 0xFFFFFFFF
                    self.on_hotkey(int(msg.wParam))
                    return True, 0
                if msg.message == WM_SHOW_SETTINGS:
                    self.on_show()
                    return True, 0
                if msg.message == WM_QUIT_REQUEST:
                    self.on_quit()
                    return True, 0
        except Exception:  # noqa: BLE001 - never break the program's message handling
            pass
        return False, 0


SINK_TITLE = "QuickSnap hotkey sink"   # a second QuickSnap.exe finds the running one by this title
WM_SHOW_SETTINGS = 0x8000 + 1          # WM_APP + 1: "please open your settings window"
WM_QUIT_REQUEST = 0x8000 + 2           # WM_APP + 2: "please quit" (sent by the installer / uninstaller)


class HotkeyManager(QObject):
    """Registers hotkeys by id; emits triggered(id) when one is pressed.
    Also emits show_requested when another QuickSnap.exe asks this one to show its settings."""

    triggered = Signal(int)
    show_requested = Signal()
    quit_requested = Signal()

    def __init__(self, app):
        super().__init__()
        self._window = QWidget()  # never shown; only its native handle is used
        self._window.setWindowTitle(SINK_TITLE)
        self.hwnd = int(self._window.winId())
        self._app = app
        self._filter = _Filter(self.hwnd, self.triggered.emit, self.show_requested.emit,
                               self.quit_requested.emit)
        app.installNativeEventFilter(self._filter)
        self._registered: set[int] = set()

    @property
    def last_delay_ms(self) -> int | None:
        return self._filter.last_delay_ms

    def close(self) -> None:
        """Release the shortcuts and stop listening (the self-check makes a temporary one)."""
        self.unregister_all()
        self._filter.active = False
        self._app.removeNativeEventFilter(self._filter)
        self._window.deleteLater()

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
