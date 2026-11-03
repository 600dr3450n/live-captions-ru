"""Render the application icons once and store them as multi-size .ico files."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"
sys.path.insert(0, str(APP))

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase, QGuiApplication, QPainter, QPixmap

app = QGuiApplication([])
for name in ("Roboto-Regular.ttf", "Roboto-Medium.ttf", "Roboto-Bold.ttf"):
    QFontDatabase.addApplicationFont(str(APP / "fonts" / name))

from icons import _draw_bubble

# A temporary directory per run: the old hardcoded user path only worked
# on one machine and left rendered PNGs behind.
TMP = Path(tempfile.mkdtemp(prefix="lcr_icons_"))


def render(captions_on: bool, sizes: tuple[int, ...], target: Path) -> None:
    frames = []
    for size in sizes:
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.scale(size / 256.0, size / 256.0)
        _draw_bubble(painter, captions_on, "")
        painter.end()
        path = TMP / f"{target.stem}_{size}.png"
        pixmap.save(str(path))
        frames.append(path)
    images = [Image.open(frame).convert("RGBA") for frame in frames]
    images[-1].save(target, format="ICO", sizes=[(size, size) for size in sizes])
    print(target.name, "готов:", target.stat().st_size, "байт, размеры:", sizes)


ON_SIZES = (16, 20, 24, 28, 32, 40, 48, 64, 96, 128, 256)
OFF_SIZES = (16, 20, 24, 32)
render(True, ON_SIZES, APP / "icon.ico")
render(False, OFF_SIZES, APP / "icon_off.ico")
shutil.copy2(APP / "icon.ico", ROOT / "assets" / "icon.ico")
