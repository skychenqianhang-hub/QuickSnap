# PyInstaller recipe:  python -m PyInstaller --noconfirm --clean QuickSnap.spec
# Output: dist\QuickSnap\QuickSnap.exe  (folder build: starts faster than a single-file exe)
from PyInstaller.utils.hooks import collect_submodules  # noqa: F401

# Qt parts QuickSnap never uses; leaving them out keeps the folder small.
EXCLUDES = [
    "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebChannel",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtSql", "PySide6.QtSvg", "PySide6.QtSvgWidgets", "PySide6.Qt3DCore", "PySide6.QtCharts",
    "PySide6.QtDataVisualization", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtBluetooth",
    "PySide6.QtPositioning", "PySide6.QtSerialPort", "PySide6.QtDesigner", "PySide6.QtHelp",
    "PySide6.QtXml", "PySide6.QtConcurrent", "PySide6.QtDBus", "tkinter", "unittest", "pydoc",
]

import os
import sys

# In a conda environment _ctypes.pyd needs ffi*.dll from Library\bin, which PyInstaller misses.
binaries = []
_conda_bin = os.path.join(os.path.dirname(sys.executable), "Library", "bin")
for _name in ("ffi.dll", "ffi-8.dll", "ffi-7.dll"):
    if os.path.isfile(os.path.join(_conda_bin, _name)):
        binaries.append((os.path.join(_conda_bin, _name), "."))

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=[("app/locales/*.json", "app/locales")],
    hiddenimports=[],
    excludes=EXCLUDES,
    noarchive=False,
)
# Drop big Qt DLLs / plugins that slip in anyway.
DROP = ("Qt6Quick", "Qt6Qml", "Qt6Pdf", "Qt6Network", "Qt6OpenGL", "Qt6Svg", "Qt6VirtualKeyboard",
        "opengl32sw", "qtwebengine", "Qt6Multimedia", "translations\\", "translations/")
a.binaries = [b for b in a.binaries if not any(d.lower() in b[0].lower() for d in DROP)]
a.datas = [d for d in a.datas if not any(x.lower() in d[0].lower() for x in DROP)]

pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="QuickSnap",
    icon="app/assets/icon.ico",
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="QuickSnap")
