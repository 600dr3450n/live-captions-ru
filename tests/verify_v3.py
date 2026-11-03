"""Version 3 verification: edit mode, dimming of previous lines, preview, tray menu, settings."""
from __future__ import annotations

import ctypes
import json
import sys
import time
from pathlib import Path

import numpy as np
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

APP_DIR = Path(__file__).resolve().parent.parent / "app"
sys.path.insert(0, str(APP_DIR))

import settings as settings_module  # noqa: E402
from overlay import PREVIEW_COMMITTED, PREVIEW_HISTORY, PREVIEW_TAIL, SubtitleOverlay, alpha_from_transparency  # noqa: E402

ART = Path(__file__).resolve().parent.parent / "_artifacts"
ART.mkdir(exist_ok=True)


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def window_under_point(x: int, y: int) -> int:
    user32 = ctypes.windll.user32
    user32.WindowFromPoint.restype = ctypes.c_void_p
    user32.WindowFromPoint.argtypes = (POINT,)
    return int(user32.WindowFromPoint(POINT(int(x), int(y))) or 0)


def check_defaults() -> bool:
    defaults = settings_module.Settings()
    expected = {
        "font_size_px": 24,
        "uppercase": True,
        "backdrop_enabled": True,
        "outline_width": 1.0,
        "line_spacing": 1.0,
        "margin": 40,
        "width_percent": 40,
        "max_lines": 2,
        "idle_clear_sec": 2,
        "tail_transparency": 40,
        "text_transparency": 0,
        "threads": 2,
    }
    actual = {
        "font_size_px": defaults.appearance.font_size_px,
        "uppercase": defaults.appearance.uppercase,
        "backdrop_enabled": defaults.appearance.backdrop_enabled,
        "outline_width": defaults.appearance.outline_width,
        "line_spacing": defaults.appearance.line_spacing,
        "margin": defaults.geometry.margin,
        "width_percent": defaults.geometry.width_percent,
        "max_lines": defaults.geometry.max_lines,
        "idle_clear_sec": defaults.behaviour.idle_clear_sec,
        "tail_transparency": defaults.appearance.tail_transparency,
        "text_transparency": defaults.appearance.text_transparency,
        "threads": defaults.audio.threads,
    }
    print("=== Настройки по умолчанию (как настроил пользователь) ===")
    ok = True
    for key, want in expected.items():
        got = actual[key]
        mark = "ок" if got == want else "ОШИБКА"
        if got != want:
            ok = False
        print(f"  {key}: {got} (ожидалось {want}) — {mark}")
    return ok


def check_migration() -> bool:
    path = settings_module.settings_path()
    backup = path.read_text(encoding="utf-8") if path.exists() else None
    old = {"appearance": {"tail_opacity": 255, "history_opacity": 50}, "version": 4}
    path.write_text(json.dumps(old), encoding="utf-8")
    loaded = settings_module.load_settings()
    migrated = loaded.appearance.tail_transparency == 80 and loaded.appearance.history_transparency == 80
    print("\n=== Миграция настроек ===")
    print(
        f"  Непрозрачности → прозрачности: активный {loaded.appearance.text_transparency}%, "
        f"неподтверждённый {loaded.appearance.tail_transparency}%, предыдущий {loaded.appearance.history_transparency}% "
        f"— {'ок' if migrated else 'ОШИБКА'}"
    )
    if backup is not None:
        path.write_text(backup, encoding="utf-8")
    else:
        path.unlink(missing_ok=True)
    return migrated


def check_click_through(app) -> bool:
    settings = settings_module.Settings()
    overlay = SubtitleOverlay(settings, exclude_from_capture=False)
    overlay.set_text("кликов", 1, 0, 1)
    for _ in range(30):
        app.processEvents()
        time.sleep(0.03)
    geometry = overlay.geometry()
    center_x = geometry.x() + geometry.width() // 2
    center_y = geometry.y() + geometry.height() // 2
    own_hwnd = int(overlay.winId())

    normal_under = window_under_point(center_x, center_y)
    overlay.begin_edit_mode()
    for _ in range(20):
        app.processEvents()
        time.sleep(0.03)
    # the window handle changes when the window is recreated — take the current one
    edit_hwnd = int(overlay.winId())
    edit_center = window_under_point(center_x, center_y)
    edit_handle = window_under_point(geometry.x() + geometry.width() - 15, geometry.y() + geometry.height() - 15)
    edit_button = window_under_point(geometry.x() + geometry.width() - 65, geometry.y() + 25)
    overlay.end_edit_mode()
    for _ in range(20):
        app.processEvents()
        time.sleep(0.03)
    after_hwnd = int(overlay.winId())
    after_under = window_under_point(center_x, center_y)

    print("\n=== Клики и режим правки (кто получает мышь в области рамки) ===")
    print(f"  Обычный режим: окно под курсором {'—' if normal_under != own_hwnd else 'НАШЕ'} (окно {normal_under}, наше {own_hwnd})")
    print(f"  Режим правки, центр рамки: {'НАШЕ' if edit_center == edit_hwnd else 'чужое'}")
    print(f"  Режим правки, ручка растягивания: {'НАШЕ' if edit_handle == edit_hwnd else 'чужое'}")
    print(f"  Режим правки, кнопка «Готово»: {'НАШЕ' if edit_button == edit_hwnd else 'чужое'}")
    print(f"  После выхода из правки: {'—' if after_under != after_hwnd else 'НАШЕ'} (наше {after_hwnd})")
    ok = (
        normal_under != own_hwnd
        and edit_center == edit_hwnd
        and edit_handle == edit_hwnd
        and edit_button == edit_hwnd
        and after_under != after_hwnd
    )
    overlay.hide()
    overlay.deleteLater()
    return ok


def check_dimming(app) -> bool:
    settings = settings_module.Settings()
    settings.appearance.uppercase = True
    settings.geometry.max_lines = 3
    overlay = SubtitleOverlay(settings, exclude_from_capture=False)
    long_text = "добрый день меня зовут анна я звоню по поводу вашего обращения в службу поддержки"
    words = long_text.split()
    overlay.set_text(long_text, len(words), len(words) - 2, len(words))
    for _ in range(30):
        app.processEvents()
        time.sleep(0.03)

    lines = overlay._lines  # noqa: SLF001
    alphas = [[word[2].alpha() for word in line_words] for line_words, _width, _x0 in lines]
    bright = alpha_from_transparency(settings.appearance.text_transparency)
    dim = alpha_from_transparency(settings.appearance.history_transparency)
    tail = alpha_from_transparency(settings.appearance.tail_transparency)
    print("\n=== Затемнение ранее сказанного ===")
    print(f"  Строк: {len(lines)}, прозрачности по строкам: {alphas}")
    older_dim = len(lines) > 1 and all(alpha == dim for alpha in alphas[0])
    current_bright = all(alpha in (bright, tail) for alpha in alphas[-1])
    print(f"  Старые строки приглушены: {'ок' if older_dim else 'ОШИБКА'}; последняя строка яркая: {'ок' if current_bright else 'ОШИБКА'}")

    overlay.set_preview(True)
    for _ in range(20):
        app.processEvents()
        time.sleep(0.02)
    preview_text = " ".join(word[1] for line, _width, _x0 in overlay._lines for word in line)  # noqa: SLF001
    preview_upper = preview_text.upper()
    preview_ok = "живые субтитры" in preview_upper.lower() and "языке" in preview_upper.lower()
    print(f"  Предпросмотр на оверлее: {'ок' if preview_ok else 'ОШИБКА'} (образец: {PREVIEW_HISTORY[:24]}… / {PREVIEW_COMMITTED})")
    print(f"  Скриншот предпросмотра: {ART / 'v3_preview_text.png'}")
    overlay.hide()
    overlay.deleteLater()
    return older_dim and current_bright and preview_ok


def check_tray_menu(app) -> bool:
    from main import CaptionsApp

    settings = settings_module.Settings()
    captions = CaptionsApp(app, settings)
    actions = [a.text() for a in captions.tray.contextMenu().actions() if not a.isSeparator()]
    expected_tail = ["Настройки", "Выход"]
    expected = [actions[0], *expected_tail] if actions else ["Включить субтитры", *expected_tail]
    first_ok = actions[0] in ("Включить субтитры", "Выключить субтитры")
    print("\n=== Меню в трее ===")
    print(f"  Пункты: {actions}")
    ok = first_ok and actions[1:] == expected_tail
    # the toggle must change both the label and the icon
    icon_before = captions.tray.icon().cacheKey()
    captions._toggle_captions()  # noqa: SLF001
    captions._update_status()  # noqa: SLF001
    actions_after = [a.text() for a in captions.tray.contextMenu().actions() if not a.isSeparator()]
    toggled = bool(actions_after) and actions_after[0] != actions[0] and actions_after[1:] == expected_tail
    icon_after = captions.tray.icon().cacheKey()
    icon_changed = icon_before != icon_after
    print(f"  После выключения: {actions_after[1:2]} — {'ок' if toggled else 'ОШИБКА'}")
    print(f"  Иконка сменилась: {'ок' if icon_changed else 'ОШИБКА'} ({icon_before} → {icon_after})")
    print(f"  Всего пунктов: {len(actions)} (ожидалось {len(expected)}) — {'ок' if ok else 'ОШИБКА'}")
    captions.tray.hide()
    return ok and toggled and icon_changed


def main() -> int:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:  # noqa: BLE001
        pass

    app = QApplication(sys.argv)
    results = {
        "defaults": check_defaults(),
        "migration": check_migration(),
        "click_through": check_click_through(app),
        "dimming": check_dimming(app),
        "tray": check_tray_menu(app),
    }
    print("\n=== ИТОГ ===")
    for name, ok in results.items():
        print(f"  {name}: {'ок' if ok else 'ОШИБКА'}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
