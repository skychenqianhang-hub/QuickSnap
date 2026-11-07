"""Write app/assets/icon.ico (all sizes) from the drawing in app/icon.py."""
from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QBuffer, QIODevice  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

app = QGuiApplication(sys.argv)
from app.icon import render  # noqa: E402

sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
pngs = []
for n in sizes:
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    render(n).save(buf, "PNG")
    pngs.append(bytes(buf.data()))

# ICO file = header + directory + PNG images (PNG-in-ICO is supported since Vista)
out = bytearray(struct.pack("<HHH", 0, 1, len(sizes)))
offset = 6 + 16 * len(sizes)
for n, data in zip(sizes, pngs):
    out += struct.pack("<BBBBHHII", n % 256, n % 256, 0, 0, 1, 32, len(data), offset)
    offset += len(data)
for data in pngs:
    out += data
dest = ROOT / "app" / "assets" / "icon.ico"
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_bytes(out)
print("wrote", dest, len(out), "bytes")
