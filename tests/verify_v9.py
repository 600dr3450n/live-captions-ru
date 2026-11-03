"""Version 11 check: top line without highlight, letter spacing, tab order, large icon."""
from __future__ import annotations

import sys
import time
from pathlib import Path

from PySide6.QtWidgets import QApplication, QListWidget

APP_DIR = Path(__file__).resolve().parent.parent / "app"
sys.path.insert(0, str(APP_DIR))

import main as app_main  # noqa: E402
import settings as settings_module  # noqa: E402
from overlay import SubtitleOverlay, alpha_from_transparency  # noqa: E402
from settings_dialog import SettingsDialog  # noqa: E402

ART = Path(__file__).resolve().parent.parent / "_artifacts"
ART.mkdir(exist_ok=True)


def check_upper_line_not_highlighted(app) -> bool:
    """Active text that has risen to the top line is drawn as "previous text"."""
    settings = settings_module.Settings()
    settings.geometry.width_px = 520
    settings.geometry.max_lines = 2
    settings.appearance.uppercase = True
    settings.appearance.backdrop_enabled = False
    overlay = SubtitleOverlay(settings, exclude_from_capture=False)
    # a phrase that certainly does not fit on one line at width 520
    text = "сегодня утром мы проверили субтитры и всё работает отлично"
    words = text.split()
    overlay.set_text(text, len(words), 0, len(words))
    for _ in range(15):
        app.processEvents()
        time.sleep(0.02)

    active_alpha = alpha_from_transparency(settings.appearance.text_transparency)
    past_alpha = alpha_from_transparency(settings.appearance.history_transparency)
    print("=== Верхняя строка не подсвечивается ===")
    print(f"  строк всего: {len(overlay._lines)}")  # noqa: SLF001
    ok = len(overlay._lines) >= 2  # noqa: SLF001
    for index, (line_words, _width, _x0) in enumerate(overlay._lines):  # noqa: SLF001
        alphas = sorted({word[2].alpha() for word in line_words})
        active_count = sum(1 for word in line_words if word[2].alpha() == active_alpha)
        past_count = sum(1 for word in line_words if word[2].alpha() == past_alpha)
        print(f"  строка {index + 1}: активных слов {active_count}, предыдущих {past_count}, оттенки {alphas}")
        last = index == len(overlay._lines) - 1  # noqa: SLF001
        if last:
            ok = ok and active_count > 0
        else:
            ok = ok and active_count == 0

    overlay.grab().toImage().save(str(ART / "v11_upper_line.png"))
    overlay.hide()
    overlay.deleteLater()
    print(f"  Подсветка только в нижней строке: {'ок' if ok else 'ОШИБКА'}")
    return ok


def check_letter_spacing(app) -> bool:
    """Letter spacing changes the text width and is visible in the image."""
    print("\n=== Межбуквенный интервал ===")
    widths = []
    for spacing in (0.0, 4.0):
        settings = settings_module.Settings()
        settings.geometry.width_px = 1200
        settings.appearance.uppercase = True
        settings.appearance.letter_spacing = spacing
        overlay = SubtitleOverlay(settings, exclude_from_capture=False)
        overlay.set_text("проверка межбуквенного интервала", 4, 0, 4)
        for _ in range(10):
            app.processEvents()
            time.sleep(0.02)
        widths.append(overlay._lines[-1][1])  # noqa: SLF001
        overlay.grab().toImage().save(str(ART / f"v11_spacing_{int(spacing)}.png"))
        overlay.hide()
        overlay.deleteLater()
    print(f"  ширина строки: 0 px → {widths[0]}, 4 px → {widths[1]}")
    ok = widths[1] > widths[0] + 40
    print(f"  Интервал увеличивает ширину: {'ок' if ok else 'ОШИБКА'}")
    return ok


def check_dialog_order_and_icon(app) -> bool:
    """The "General" section is first; the icon has no frame and fills its full size."""
    print("\n=== Разделы настроек и иконка ===")
    dialog = SettingsDialog(
        settings_module.Settings(), on_change=lambda s: None, on_apply=lambda s: None, on_edit_box=lambda: None
    )
    dialog.show()
    for _ in range(20):
        app.processEvents()
        time.sleep(0.02)
    nav = dialog.findChild(QListWidget)
    titles = [nav.item(index).text() for index in range(nav.count())]
    print(f"  разделы: {titles}")
    order_ok = titles[0] == "Общие" and nav.currentRow() == 0
    spacing_row = hasattr(dialog, "letter_spin")
    print(f"  «Общее» первым и открыто по умолчанию: {'ок' if order_ok else 'ОШИБКА'}")
    print(f"  Поле межбуквенного интервала есть: {'ок' if spacing_row else 'ОШИБКА'}")
    dialog.close()

    sizes = []
    for size in (16, 32, 256):
        pixmap = app_main.make_icon(True).pixmap(size, size)
        pixmap.save(str(ART / f"v11_icon_{size}.png"))
        image = pixmap.toImage()
        filled = sum(
            1
            for y in range(image.height())
            for x in range(image.width())
            if image.pixelColor(x, y).alpha() > 200
        )
        sizes.append(filled / (size * size))
        print(f"  иконка {size}×{size}: заполнено {sizes[-1] * 100:.0f} % площади")
    icon_ok = all(share > 0.6 for share in sizes)
    print(f"  Иконка занимает почти всю площадь (без рамки): {'ок' if icon_ok else 'ОШИБКА'}")
    return order_ok and spacing_row and icon_ok


def main() -> int:
    app = QApplication(sys.argv)
    results = {
        "upper_line": check_upper_line_not_highlighted(app),
        "letter_spacing": check_letter_spacing(app),
        "dialog_and_icon": check_dialog_order_and_icon(app),
    }
    print("\n=== ИТОГ ===")
    for name, ok in results.items():
        print(f"  {name}: {'ок' if ok else 'ОШИБКА'}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
