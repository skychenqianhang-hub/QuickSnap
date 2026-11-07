"""List every tr("...") string in app/ and report what zh.json / ja.json are missing.

    python tools_dev/i18n_check.py          -> report, exit 1 if anything is missing
    python tools_dev/i18n_check.py --keys   -> just print the English strings
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def collect() -> list[str]:
    keys: list[str] = []
    files = sorted((ROOT / "app").rglob("*.py")) + [ROOT / "main.py"]
    for f in files:
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and node.args
                    and ((isinstance(node.func, ast.Name) and node.func.id in ("tr", "tr_noop"))
                         or (isinstance(node.func, ast.Attribute) and node.func.attr == "tr"))
                    and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                if node.args[0].value not in keys:
                    keys.append(node.args[0].value)
    return keys


def main() -> int:
    keys = collect()
    if "--keys" in sys.argv:
        for k in keys:
            print(json.dumps(k, ensure_ascii=False))
        return 0
    bad = 0
    for lang in ("zh", "ja"):
        path = ROOT / "app" / "locales" / f"{lang}.json"
        table = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        missing = [k for k in keys if not table.get(k)]
        extra = [k for k in table if k not in keys]
        for k in missing:
            print(f"[{lang}] missing: {k!r}")
        for k in extra:
            print(f"[{lang}] unused:  {k!r}")
        bad += len(missing)
    print(f"{len(keys)} strings; {'OK' if not bad else f'{bad} missing'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
