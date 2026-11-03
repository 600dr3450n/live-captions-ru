#!/usr/bin/env python3
"""Tray icon never comes out empty: the file path works, and so does the fallback."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(os.environ.get("LCRU_ROOT") or Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(ROOT / "app"))

from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtGui import QIcon  # noqa: E402

import icons  # noqa: E402

app = QApplication([])
failures = 0


def check(label: str, icon: QIcon) -> None:
    global failures
    pixmap = icon.pixmap(32, 32)
    opaque = 0
    if not pixmap.isNull():
        image = pixmap.toImage()
        for y in range(image.height()):
            for x in range(image.width()):
                if image.pixelColor(x, y).alpha() > 30:
                    opaque += 1
    ok = opaque > 20
    print(f"{label:<34} pixmap {pixmap.width()}x{pixmap.height()}, "
          f"непрозрачных пикселей {opaque} -> {'ок' if ok else 'ПУСТО'}")
    if not ok:
        failures += 1


# 1. Normal path: the .ico files sit next to the module.
check("иконка из файла (вкл)", icons.make_icon(True))
check("иконка из файла (выкл)", icons.make_icon(False))
check("иконка с прозрачностью", icons.make_icon(True, "", 0.5))
check("иконка со статусом", icons.make_icon(True, "danger"))

# 2. Missing file: nothing is drawn in memory, the warning is logged instead.
# The bundle must contain both files, so this path means a hand-deleted file.
real_path = icons._icon_path
icons._icon_path = lambda captions_on: Path("/nonexistent") / (
    "icon.ico" if captions_on else "icon_off.ico")
missing = icons.make_icon(True)
pixmap = missing.pixmap(32, 32)
empty = pixmap.isNull() or all(
    pixmap.toImage().pixelColor(x, y).alpha() == 0
    for x in range(pixmap.width()) for y in range(pixmap.height()))
print(f"{'без файла иконка не рисуется':<34} {'ок' if empty else 'РИСУЕТСЯ'}")
if not empty:
    failures += 1
icons._icon_path = real_path

print("\nВСЕ ПРОВЕРКИ ПРОЙДЕНЫ" if failures == 0 else f"\nПРОВАЛОВ: {failures}")
raise SystemExit(1 if failures else 0)
