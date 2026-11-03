"""Проверка версии 7: центровка предпросмотра, реакция рамки на настройки, дефолты пользователя."""
from __future__ import annotations

import ctypes
import sys
import time
from pathlib import Path

from PySide6.QtWidgets import QApplication

APP_DIR = Path(__file__).resolve().parent.parent / "app"
sys.path.insert(0, str(APP_DIR))

import settings as settings_module  # noqa: E402
from overlay import SubtitleOverlay, alpha_from_transparency  # noqa: E402

ART = Path(__file__).resolve().parent.parent / "_artifacts"
ART.mkdir(exist_ok=True)


def check_defaults_match_user() -> bool:
    defaults = settings_module.Settings()
    expected = {
        "font_size_px": 24,
        "uppercase": True,
        "bold": True,
        "align": "left",
        "text_transparency": 0,
        "tail_transparency": 40,
        "history_transparency": 40,
        "outline_enabled": True,
        "outline_color": "#000000",
        "outline_transparency": 20,
        "outline_width": 1.0,
        "backdrop_enabled": True,
        "backdrop_color": "#000000",
        "backdrop_transparency": 40,
        "corner_radius": 6,
        "padding_x": 12,
        "padding_y": 12,
        "letter_spacing": 0.0,
        "margin": 40,
        "width_percent": 40,
        "max_lines": 2,
        "idle_clear_sec": 2,
        "highlight_seconds": 2.0,
        "threads": 2,
    }
    actual = {
        "font_size_px": defaults.appearance.font_size_px,
        "uppercase": defaults.appearance.uppercase,
        "bold": defaults.appearance.bold,
        "align": defaults.appearance.align,
        "text_transparency": defaults.appearance.text_transparency,
        "tail_transparency": defaults.appearance.tail_transparency,
        "history_transparency": defaults.appearance.history_transparency,
        "outline_enabled": defaults.appearance.outline_enabled,
        "outline_color": defaults.appearance.outline_color,
        "outline_transparency": defaults.appearance.outline_transparency,
        "outline_width": defaults.appearance.outline_width,
        "backdrop_enabled": defaults.appearance.backdrop_enabled,
        "backdrop_color": defaults.appearance.backdrop_color,
        "backdrop_transparency": defaults.appearance.backdrop_transparency,
        "corner_radius": defaults.appearance.corner_radius,
        "padding_x": defaults.appearance.padding_x,
        "padding_y": defaults.appearance.padding_y,
        "letter_spacing": defaults.appearance.letter_spacing,
        "margin": defaults.geometry.margin,
        "width_percent": defaults.geometry.width_percent,
        "max_lines": defaults.geometry.max_lines,
        "idle_clear_sec": defaults.behaviour.idle_clear_sec,
        "highlight_seconds": defaults.behaviour.highlight_seconds,
        "threads": defaults.audio.threads,
    }
    print("=== Настройки по умолчанию = настройки пользователя ===")
    failures = []
    for key, want in expected.items():
        got = actual[key]
        if got != want:
            failures.append(f"{key}: {got} вместо {want}")
    if failures:
        print("  Отличия: " + "; ".join(failures))
    else:
        print(f"  Все {len(expected)} значений совпадают")
    return not failures


def check_preview_align(app) -> bool:
    settings = settings_module.Settings()
    settings.geometry.width_px = 1000
    settings.geometry.max_lines = 3
    overlay = SubtitleOverlay(settings, exclude_from_capture=False)
    overlay.set_preview(True)
    for _ in range(30):
        app.processEvents()
        time.sleep(0.02)

    print("\n=== Предпросмотр: выравнивание и активное слово ===")
    box_width = overlay.width()
    last_words, line_width, x0 = overlay._lines[-1]  # noqa: SLF001
    left_ok = abs(x0 - settings.appearance.padding_x) <= 1
    print(f"  Строка прижата влево: начало {x0:.0f} при отступе {settings.appearance.padding_x} — "
          f"{'ок' if left_ok else 'ОШИБКА'}")

    highlight = [word for word in last_words if word[2].alpha() == 255]
    active_text = " ".join(word[1] for word in highlight)
    expected_active = "ЖИВЫЕ СУБТИТРЫ НА РУССКОМ"
    print(f"  Подсвечен активный сегмент: {active_text!r} — {'ок' if active_text == expected_active else 'ОШИБКА'}")

    overlay.grab().toImage().save(str(ART / "v7_preview.png"))
    overlay.hide()
    overlay.deleteLater()
    return left_ok and active_text == expected_active


def check_frame_reaction(app) -> bool:
    settings = settings_module.Settings()
    settings.geometry.width_px = 900
    settings.geometry.max_lines = 2
    overlay = SubtitleOverlay(settings, exclude_from_capture=False)
    overlay.set_preview(True)
    for _ in range(20):
        app.processEvents()
        time.sleep(0.02)
    first = (overlay.width(), overlay.height())

    settings.geometry.width_px = 600
    settings.geometry.max_lines = 4
    overlay.apply_settings(settings)  # так же, как это делает окно настроек
    for _ in range(20):
        app.processEvents()
        time.sleep(0.02)
    second = (overlay.width(), overlay.height())

    print("\n=== Рамка реагирует на настройки в предпросмотре ===")
    print(f"  Было {first[0]}x{first[1]}, стало {second[0]}x{second[1]}")
    ok = second[0] == 600 and second[1] > first[1]
    print(f"  {'ок' if ok else 'ОШИБКА'}")
    overlay.hide()
    overlay.deleteLater()
    return ok


def check_preview_transparency(app) -> bool:
    """В образце: активное — только «СУБТИТРОВ», неподтверждённое — хвост, история — первая строка."""
    settings = settings_module.Settings()
    settings.appearance.uppercase = True
    settings.geometry.width_px = 1100
    settings.geometry.max_lines = 3
    overlay = SubtitleOverlay(settings, exclude_from_capture=False)
    overlay.set_preview(True)
    for _ in range(20):
        app.processEvents()
        time.sleep(0.02)

    active_alpha = alpha_from_transparency(settings.appearance.text_transparency)
    unconfirmed_alpha = alpha_from_transparency(settings.appearance.tail_transparency)
    past_alpha = alpha_from_transparency(settings.appearance.history_transparency)
    history_words, active_words = overlay._lines[0][0], overlay._lines[-1][0]  # noqa: SLF001

    print("\n=== Образец предпросмотра и ползунки прозрачности ===")
    history_ok = bool(history_words) and all(word[2].alpha() == past_alpha for word in history_words)
    print(f"  Первая строка — «предыдущий текст»: {'ок' if history_ok else 'ОШИБКА'}")
    active_text = [word[1] for word in active_words if word[2].alpha() == active_alpha]
    active_ok = " ".join(active_text) == "ЖИВЫЕ СУБТИТРЫ НА РУССКОМ"
    print(f"  «Активный текст» — только активное слово: {active_text} — {'ок' if active_ok else 'ОШИБКА'}")
    tail_text = [word[1] for word in active_words if word[2].alpha() == unconfirmed_alpha]
    tail_ok = [word.upper() for word in tail_text] == ["ЯЗЫКЕ"]
    print(f"  «Неподтверждённый текст» — хвост фразы: {tail_text} — {'ок' if tail_ok else 'ОШИБКА'}")

    overlay.set_preview(False)
    for _ in range(5):
        app.processEvents()
    overlay.hide()
    overlay.deleteLater()
    return history_ok and active_ok and tail_ok


def check_word_fits_box(app) -> bool:
    """Недописанное слово не должно вылезать за подложку."""
    settings = settings_module.Settings()
    settings.geometry.width_px = 460
    settings.geometry.max_lines = 3
    settings.appearance.font_size_px = 24
    settings.appearance.uppercase = True
    overlay = SubtitleOverlay(settings, exclude_from_capture=False)
    overlay.set_text("привет как дела хорошо сегодня утром", 5, 4, 5)
    for _ in range(20):
        app.processEvents()
        time.sleep(0.02)

    print("\n=== Последнее (недописанное) слово внутри подложки ===")
    inner = overlay.width() - 2 * settings.appearance.padding_x
    metrics = overlay._metrics  # noqa: SLF001
    overflow = []
    for line_words, _width, x0 in overlay._lines:  # noqa: SLF001
        for word_x, word, _color in line_words:
            right = x0 + word_x + metrics.horizontalAdvance(word)
            if right > inner + 1:
                overflow.append((word, round(right), round(inner)))
    print(f"  Поле вывода: {round(inner)} px, строк: {len(overlay._lines)}")  # noqa: SLF001
    print(f"  Слова за границей: {overflow if overflow else 'нет'} — {'ок' if not overflow else 'ОШИБКА'}")

    overlay.grab().toImage().save(str(ART / "v7_words_fit.png"))
    overlay.hide()
    overlay.deleteLater()
    return not overflow


def main() -> int:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:  # noqa: BLE001
        pass
    app = QApplication(sys.argv)
    results = {
        "defaults": check_defaults_match_user(),
        "preview_align": check_preview_align(app),
        "preview_transparency": check_preview_transparency(app),
        "words_fit_box": check_word_fits_box(app),
        "frame_reaction": check_frame_reaction(app),
    }
    print("\n=== ИТОГ ===")
    for name, ok in results.items():
        print(f"  {name}: {'ок' if ok else 'ОШИБКА'}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
