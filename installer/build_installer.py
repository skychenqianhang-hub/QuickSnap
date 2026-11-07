"""One step from source to installer: automatic tests -> PyInstaller -> self-check -> Inno Setup.

Run from the project folder:  python installer/build_installer.py [--skip-pyinstaller]
Output: installer/output/QuickSnap-Setup-<version>.exe
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.version import __version__  # noqa: E402

ISCC_CANDIDATES = [
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe",
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Inno Setup 6" / "ISCC.exe",
]


def main() -> int:
    os.chdir(ROOT)
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    print("1/4 automatic tests ...")
    r = subprocess.run([sys.executable, "-m", "tests.test_core"], env=env, capture_output=True, text=True,
                       encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-3000:], r.stderr[-3000:])
        print("Tests failed - no installer.")
        return 1
    if "--skip-pyinstaller" not in sys.argv:
        print("2/4 PyInstaller ...")
        subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "QuickSnap.spec"],
                       check=True, capture_output=True)
    exe = ROOT / "dist" / "QuickSnap" / "QuickSnap.exe"
    if not exe.exists():
        print("Missing", exe)
        return 1
    print("3/4 self-check of the packaged exe ...")
    report = ROOT / "dist" / "selfcheck.txt"
    r = subprocess.run([str(exe), "--check", str(report)], timeout=120)
    text = report.read_text(encoding="utf-8") if report.exists() else ""
    if r.returncode != 0 or not text.strip().endswith("ALL PASSED"):
        print(text)
        print("Self-check failed - no installer.")
        return 1
    iscc = next((p for p in ISCC_CANDIDATES if p.exists()), None)
    if iscc is None:
        print("Inno Setup (ISCC.exe) not found. Install it: winget install JRSoftware.InnoSetup")
        return 1
    print(f"4/4 Inno Setup, version {__version__} ...")
    subprocess.run([str(iscc), "/Q", f"/DAppVersion={__version__}", str(ROOT / "installer" / "QuickSnap.iss")],
                   check=True)
    out = ROOT / "installer" / "output" / f"QuickSnap-Setup-{__version__}.exe"
    print("Done:", out, f"({out.stat().st_size / 1e6:.0f} MB)" if out.exists() else "(file missing?)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
