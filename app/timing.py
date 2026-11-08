"""Timing log: how long each step between the hotkey and the visible capture screen took.

One line per screenshot in %APPDATA%\\QuickSnap\\timing.log (times only — never any
picture or window title). Kept small: above 100 KB only the newest 300 lines stay.
Used to find out where a slow start comes from.
"""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from .config import config_dir

MAX_BYTES = 100_000
KEEP_LINES = 300


def log_path() -> Path:
    return config_dir() / "timing.log"


def write_line(text: str) -> None:
    path = log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {text}\n")
        if path.stat().st_size > MAX_BYTES:
            lines = path.read_text(encoding="utf-8").splitlines()[-KEEP_LINES:]
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError:
        pass  # a missing log must never break screenshots


class CaptureTimer:
    """Collects the step times of one screenshot; finish() writes the line."""

    def __init__(self, source: str, key_delay_ms: int | None, idle_s: float | None, first: bool):
        self.t0 = time.perf_counter()
        self.source = source            # "hotkey" or "tray"
        self.key_delay_ms = key_delay_ms
        self.idle_s = idle_s
        self.first = first
        self.steps: list[tuple[str, float]] = []
        self._last = self.t0
        self.done = False

    def mark(self, name: str) -> None:
        now = time.perf_counter()
        self.steps.append((name, (now - self._last) * 1000))
        self._last = now

    def finish(self) -> str:
        """Call when the capture screen has been drawn for the first time."""
        if self.done:
            return ""
        self.done = True
        self.mark("first drawing")
        total = (self._last - self.t0) * 1000
        parts = [f"{n} {ms:.0f}" for n, ms in self.steps]
        key = f"key->program {self.key_delay_ms} ms | " if self.key_delay_ms is not None else ""
        idle = f"idle {self.idle_s:.0f} s" if self.idle_s is not None else "idle -"
        line = (f"{self.source:6s} | {key}" + " | ".join(parts) + f" | TOTAL {total:.0f} ms"
                + f" | {idle}" + (" | first since start" if self.first else ""))
        write_line(line)
        return line
