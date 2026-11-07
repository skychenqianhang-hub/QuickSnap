"""Interface languages.

Write interface text in English inside tr():
    tr("Copy")                     -> text in the current language
    tr("Saved to {0}", path)       -> translate the template, then fill in values
English is the source language and the key of every table; a missing
translation falls back to English. Tables: app/locales/<code>.json,
format {"English": "translation"}.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

LANGUAGES = {"en": "English", "zh": "简体中文", "ja": "日本語"}  # each in its own script
DEFAULT_LANGUAGE = "en"

_current = DEFAULT_LANGUAGE
_table: dict[str, str] = {}


def locales_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "app" / "locales"


def load_table(lang: str) -> dict[str, str]:
    if lang == "en":
        return {}
    try:
        data = json.loads((locales_dir() / f"{lang}.json").read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in data.items() if v}
    except (OSError, json.JSONDecodeError):
        return {}


def set_language(lang: str) -> str:
    global _current, _table
    if lang not in LANGUAGES:
        lang = DEFAULT_LANGUAGE
    _current = lang
    _table = load_table(lang)
    return lang


def current_language() -> str:
    return _current


def tr(text: str, *args) -> str:
    out = _table.get(text, text)
    return out.format(*args) if args else out


def tr_noop(text: str) -> str:
    """Marks text that is translated later with tr(variable); tools_dev/i18n_check.py finds it."""
    return text
