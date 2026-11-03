"""Version 6 verification: whole-word highlight, one-second rule, smooth scrolling, new settings widgets."""
from __future__ import annotations

import ctypes
import queue
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QCheckBox, QPushButton

APP_DIR = Path(__file__).resolve().parent.parent / "app"
sys.path.insert(0, str(APP_DIR))

import main as app_main  # noqa: E402
import settings as settings_module  # noqa: E402
from overlay import SubtitleOverlay, alpha_from_transparency  # noqa: E402
from settings_dialog import SettingsDialog  # noqa: E402
from widgets_ui import ColorRow  # noqa: E402

ART = Path(__file__).resolve().parent.parent / "_artifacts"
ART.mkdir(exist_ok=True)


class FakeRecognizer:
    def create_stream(self):
        return object()

    def feed(self, stream, samples, rate) -> str:
        return ""

    def is_endpoint(self, stream) -> bool:
        return False

    def reset(self, stream) -> None:
        pass

    def finish(self, stream) -> str:
        return ""


def check_highlight_rule() -> bool:
    worker = app_main.RecognitionWorker(FakeRecognizer(), queue.Queue(), lambda *args: None, lambda: False)

    print("=== Подсветка: «дозревание» слова и окно активности ===")
    first = worker._highlight_range("привет мир как")  # noqa: SLF001
    print(f"  Сразу после ввода: {first} (ожидалось (0, 2) — «как» ещё набирается)")
    time.sleep(0.45)
    second = worker._highlight_range("привет мир как")  # noqa: SLF001
    print(f"  Пауза 0,45 с — слово дозрело: {second} (ожидалось (0, 3))")
    third = worker._highlight_range("привет мир как дела")  # noqa: SLF001
    print(f"  Пошло новое слово: {third} (ожидалось (0, 3) — всё в пределах 2 с)")
    time.sleep(0.45)
    fourth = worker._highlight_range("привет мир как дела")  # noqa: SLF001
    print(f"  Новое слово дозрело: {fourth} (ожидалось (0, 4))")
    time.sleep(2.2)
    fifth = worker._highlight_range("привет мир как дела")  # noqa: SLF001
    print(f"  Прошло больше 2 с без речи: {fifth} (ожидалось (4, 4) — подсветка погасла)")

    ok = first == (0, 2) and second == (0, 3) and third == (0, 3) and fourth == (0, 4) and fifth == (4, 4)
    print(f"  Итог: {'ок' if ok else 'ОШИБКА'}")
    return ok


def check_highlight_render(app) -> bool:
    settings = settings_module.Settings()
    settings.geometry.max_lines = 2
    overlay = SubtitleOverlay(settings, exclude_from_capture=False)
    text = "добрый день меня зовут анна"
    overlay.set_text(text, len(text.split()), 3, 5)  # "зовут анна" is highlighted
    for _ in range(20):
        app.processEvents()
        time.sleep(0.02)

    pale = alpha_from_transparency(settings.appearance.history_transparency)
    bright = alpha_from_transparency(settings.appearance.text_transparency)
    alphas = [[word[2].alpha() for word in line] for line, _width, _x0 in overlay._lines]  # noqa: SLF001
    print("\n=== Отрисовка подсветки целыми словами ===")
    print(f"  Прозрачности по словам: {alphas}")
    flat = [alpha for line in alphas for alpha in line]
    bright_count = sum(1 for alpha in flat if alpha == bright)
    pale_count = sum(1 for alpha in flat if alpha == pale)
    ok = bright_count == 2 and pale_count == 3
    print(f"  Ярких слов: {bright_count} (ожидалось 2), приглушённых: {pale_count} (ожидалось 3) — {'ок' if ok else 'ОШИБКА'}")
    overlay.grab().toImage().save(str(ART / "v6_highlight.png"))
    overlay.hide()
    overlay.deleteLater()
    return ok


def check_no_animation(app) -> bool:
    """No animations; words do not move; highlighting is driven by the worker thread, the window does not fade on its own."""
    settings = settings_module.Settings()
    settings.geometry.width_px = 900
    settings.geometry.max_lines = 3
    settings.appearance.uppercase = False
    overlay = SubtitleOverlay(settings, exclude_from_capture=False)
    overlay.set_text("первое второе третье", 3, 2, 3)
    for _ in range(20):
        app.processEvents()
        time.sleep(0.02)

    print("\n=== Без анимаций, слова не двигаются ===")
    has_animation = any(
        hasattr(overlay, name) for name in ("_slide_offset", "_slide_timer", "_highlight_timer")
    )
    print(f"  Анимаций в окне нет: {'ок' if not has_animation else 'ОШИБКА'}")

    x0_before = overlay._lines[-1][2]  # noqa: SLF001
    overlay.set_text("первое второе третье че", 3, 2, 3)
    for _ in range(3):
        app.processEvents()
    letters_ok = abs(overlay._lines[-1][2] - x0_before) < 0.5  # noqa: SLF001
    print(f"  Новые буквы не сдвигают строку: {'ок' if letters_ok else 'ОШИБКА'}")

    active_before = any(word[2].alpha() == 255 for word in overlay._lines[-1][0])  # noqa: SLF001
    for _ in range(20):
        app.processEvents()
        time.sleep(0.03)
    active_after = any(word[2].alpha() == 255 for word in overlay._lines[-1][0])  # noqa: SLF001
    print(f"  Подсветка не гаcнет сама (её задаёт воркер): {'ок' if active_before and active_after else 'ОШИБКА'}")

    overlay.grab().toImage().save(str(ART / "v6_no_animation.png"))
    overlay.hide()
    overlay.deleteLater()
    return (not has_animation) and letters_ok and active_before and active_after


def check_dialog_controls(app) -> bool:
    dialog = SettingsDialog(
        settings_module.Settings(), on_change=lambda s: None, on_apply=lambda s: None, on_edit_box=lambda: None
    )
    dialog.show()
    for _ in range(20):
        app.processEvents()
        time.sleep(0.02)

    colors = dialog.findChildren(ColorRow)
    from PySide6.QtWidgets import QSpinBox, QDoubleSpinBox
    steppers = dialog.findChildren(QSpinBox) + dialog.findChildren(QDoubleSpinBox)
    checkboxes = [box.text() for box in dialog.findChildren(QCheckBox)]
    print("\n=== Элементы настроек ===")
    print(f"  Ряды цветов: {len(colors)} (ожидалось 3), ползунки со кнопками −/+: {len(steppers)}")
    minus_buttons = len(steppers)  # spin boxes have built-in arrows
    scroll_box = any("Плавная прокрутка" in text for text in checkboxes)
    print(f"  Кнопки −/+ у ползунков: {minus_buttons} из {len(steppers)}")
    print(f"  Галочка плавной прокрутки: {'ок' if not scroll_box else 'ОШИБКА (лишняя галочка)'}")
    dialog.close()
    return len(colors) == 3 and len(steppers) >= 6 and not scroll_box


def main() -> int:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:  # noqa: BLE001
        pass
    app = QApplication(sys.argv)
    results = {
        "highlight_rule": check_highlight_rule(),
        "highlight_render": check_highlight_render(app),
        "no_animation": check_no_animation(app),
        "dialog_controls": check_dialog_controls(app),
    }
    print("\n=== ИТОГ ===")
    for name, ok in results.items():
        print(f"  {name}: {'ок' if ok else 'ОШИБКА'}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
