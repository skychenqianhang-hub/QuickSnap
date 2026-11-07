"""`QuickSnap.exe --check result.txt` — quick health check of a packaged build.

Runs without touching the user's settings (uses a temporary config folder)
and without leaving anything registered. Last line is "ALL PASSED" on success;
exit code 0 = passed, 1 = something failed.
"""
from __future__ import annotations

import json
import os
import tempfile
import traceback
from pathlib import Path


def run(result_path: str) -> int:
    lines: list[str] = []
    failed = False

    def check(name, fn):
        nonlocal failed
        try:
            detail = fn()
            lines.append(f"OK   {name}" + (f" — {detail}" if detail else ""))
        except Exception:  # noqa: BLE001 - report everything
            failed = True
            lines.append(f"FAIL {name}\n" + traceback.format_exc())

    tmp = tempfile.mkdtemp(prefix="quicksnap_check_")
    os.environ["QUICKSNAP_CONFIG_DIR"] = tmp

    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    from app import capture, i18n, win32
    from app.config import Config
    from app.controller import unique_path
    from app.hotkey import HotkeyManager, normalize, parse
    from app.icon import app_icon
    from app.overlay import CaptureSession
    from app.version import __version__

    lines.append(f"QuickSnap {__version__}")

    def t_monitors():
        mons = win32.list_monitors()
        assert mons, "no monitors found"
        return "; ".join(f"{m.width}x{m.height} at ({m.left},{m.top})" + (" primary" if m.primary else "")
                         for m in mons)

    def t_windows():
        import os as _os
        wins = win32.list_windows(exclude_pid=_os.getpid())
        return f"{len(wins)} visible window(s) found"

    shots_box = {}

    def t_grab():
        shots = capture.grab_all()
        assert shots
        for s in shots:
            assert (s.image.width(), s.image.height()) == (s.monitor.width, s.monitor.height)
            assert not s.image.isNull()
        shots_box["shots"] = shots
        return f"{len(shots)} monitor picture(s)"

    def t_overlay():
        session = CaptureSession(shots_box["shots"])
        try:
            assert session.overlays, "no capture windows"
            for ov in session.overlays:
                assert ov.shot is not None, "capture window not matched to a monitor"
                ov.select_all()
                img = ov.cropped()
                assert img is not None and img.width() == ov.shot.monitor.width
            return f"{len(session.overlays)} capture window(s) matched"
        finally:
            session.close()

    def t_clipboard():
        img = shots_box["shots"][0].image.copy(0, 0, 64, 48)
        cb = app.clipboard()
        backup = cb.mimeData()
        saved = {f: bytes(backup.data(f)) for f in backup.formats()} if backup else {}
        cb.setImage(img)
        app.processEvents()
        back = cb.image()
        assert (back.width(), back.height()) == (64, 48), back.size()
        # put back what the user had (text etc.)
        if saved:
            from PySide6.QtCore import QMimeData
            md = QMimeData()
            for f, data in saved.items():
                md.setData(f, data)
            cb.setMimeData(md)
        return "image round-trip ok"

    def t_hotkey():
        assert parse("Ctrl+Alt+A") == (win32.MOD_CONTROL | win32.MOD_ALT, ord("A"))
        assert normalize("alt+ctrl+a") == "Ctrl+Alt+A"
        hk = HotkeyManager(app)
        ok = hk.register(99, "Ctrl+Alt+Shift+F11")
        hk.unregister_all()
        return "register/unregister ok" if ok else "parse ok (test combo taken by another program)"

    def t_config():
        cfg = Config(Path(tmp) / "config.json")
        assert cfg["hotkey"] == "Ctrl+Alt+A" and cfg["language"] == "en"
        assert cfg["save_dir"]
        data = json.loads((Path(tmp) / "config.json").read_text(encoding="utf-8"))
        assert data["save_dir"] == cfg["save_dir"]
        return f"default screenshot folder: {cfg['save_dir']}"

    def t_save():
        folder = Path(tmp) / "shots"
        folder.mkdir()
        p = unique_path(folder)
        assert shots_box["shots"][0].image.copy(0, 0, 32, 32).save(str(p))
        assert p.stat().st_size > 0
        return p.name

    def t_i18n():
        for lang in ("zh", "ja"):
            table = i18n.load_table(lang)
            assert len(table) >= 10, f"{lang} table missing"
        return "zh / ja tables loaded"

    def t_icon():
        assert not app_icon().isNull()

    for name, fn in [("monitors", t_monitors), ("windows", t_windows),("screen copy", t_grab), ("capture windows", t_overlay),
                     ("clipboard", t_clipboard), ("hotkey", t_hotkey), ("settings", t_config),
                     ("save png", t_save), ("languages", t_i18n), ("icon", t_icon)]:
        if name in ("capture windows", "clipboard", "save png") and "shots" not in shots_box:
            lines.append(f"SKIP {name} (no screen picture)")
            failed = True
            continue
        check(name, fn)

    lines.append("SOME CHECKS FAILED" if failed else "ALL PASSED")
    Path(result_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 1 if failed else 0
