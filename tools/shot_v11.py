"""Скриншоты: окно цвета, режим правки рамки, предпросмотр без ЗАГЛАВНЫХ; проверка выравнивания."""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

from PySide6.QtWidgets import QApplication  # noqa: E402

import settings as sm  # noqa: E402
from color_dialog import ColorDialog  # noqa: E402
from overlay import SubtitleOverlay  # noqa: E402

ART = ROOT / "_artifacts"
app = QApplication([])


def pump(delay: float = 0.15) -> None:
    deadline = time.time() + delay
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)


# ---------------------------------------------------------------- окно цвета
dialog = ColorDialog(sm.QColor("#56436D") if hasattr(sm, "QColor") else None) if False else None
from PySide6.QtGui import QColor  # noqa: E402

dialog = ColorDialog(QColor("#56436D"))
dialog.show()
pump()
dialog.grab().save(str(ART / "v11_color_dialog.png"))
print("скриншот:", ART / "v11_color_dialog.png", dialog.width(), "x", dialog.height())
dialog.close()

# ------------------------------------------------------------------ рамка, правка
s = sm.Settings()
s.geometry.width_px = 760
s.geometry.max_lines = 3
s.appearance.uppercase = False
overlay = SubtitleOverlay(s, exclude_from_capture=False)
overlay.set_preview(True)
pump()
overlay.begin_edit_mode()
pump()
overlay.grab().save(str(ART / "v11_edit_mode.png"))
print("скриншот:", ART / "v11_edit_mode.png")
overlay.end_edit_mode(save=False)

# ------------------------------------------------ предпросмотр без ЗАГЛАВНЫХ
overlay.apply_settings(s)
pump()
overlay.grab().save(str(ART / "v11_preview_lower.png"))
print("скриншот:", ART / "v11_preview_lower.png")
overlay.deleteLater()

# ------------------------------------------------------- выравнивание и хвост
print("\n=== Выравнивание с недописанным словом ===")
ok = True
for align in ("left", "center", "right"):
    s = sm.Settings()
    s.geometry.width_px = 600
    s.geometry.max_lines = 2
    s.appearance.align = align
    s.appearance.uppercase = True
    s.appearance.backdrop_enabled = False
    overlay = SubtitleOverlay(s, exclude_from_capture=False)
    text = "ну сейчас к тебе приедет бригада давай я жду"
    confirmed = 6  # «давай» ещё пишется
    overlay.set_text([], text, confirmed, 0, confirmed)
    pump(0.2)
    image = overlay.grab().toImage()
    xs = [x for y in range(image.height()) for x in range(image.width()) if image.pixelColor(x, y).alpha() > 40]
    inside = (not xs) or (min(xs) >= 8 and max(xs) <= image.width() - 8)
    print(f"  {align:6}: чернила {min(xs)}..{max(xs)} из {image.width()} — {'ок' if inside else 'ВЫХОД ЗА РАМКУ'}")
    ok = ok and inside
    overlay.deleteLater()
print("=== ИТОГ ===", "ок" if ok else "ОШИБКА")
