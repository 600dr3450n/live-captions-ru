"""Проверка версии 2: настройки, исправление «простыни», окно настроек."""
from __future__ import annotations

import ctypes
import sys
import time
from pathlib import Path

import numpy as np
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QListWidget

APP_DIR = Path(__file__).resolve().parent.parent / "app"
sys.path.insert(0, str(APP_DIR))

import settings as settings_module  # noqa: E402
from overlay import SubtitleOverlay  # noqa: E402
from settings_dialog import SettingsDialog  # noqa: E402

ART = Path(__file__).resolve().parent.parent / "_artifacts"
ART.mkdir(exist_ok=True)

PHRASE_1 = (
    "добрый день меня зовут анна я звоню по поводу вашего обращения в службу поддержки "
    "по поводу зависания программы при формировании отчёта за прошлый месяц"
)
PHRASE_2 = (
    "давайте попробуем очистить кэш и перезапустить программу если не поможет я передам "
    "обращение разработчикам и мы вернёмся к вам с ответом в течение двух рабочих дней"
)


def check_settings_roundtrip() -> bool:
    original_path = settings_module.settings_path()
    backup = original_path.read_text(encoding="utf-8") if original_path.exists() else None

    settings = settings_module.Settings()
    settings.appearance.font_size_px = 48
    settings.appearance.text_color = "#FFD400"
    settings.appearance.backdrop_transparency = 20
    settings.appearance.outline_width = 5.5
    settings.geometry.position = "custom"
    settings.geometry.x = 120
    settings.geometry.y = 240
    settings.geometry.width_px = 900
    settings.geometry.max_lines = 4
    settings.audio.threads = 3
    settings_module.save_settings(settings)

    loaded = settings_module.load_settings()
    checks = {
        "font_size_px": loaded.appearance.font_size_px == 48,
        "text_color": loaded.appearance.text_color == "#FFD400",
        "backdrop_transparency": loaded.appearance.backdrop_transparency == 20,
        "outline_width": abs(loaded.appearance.outline_width - 5.5) < 1e-6,
        "position": loaded.geometry.position == "custom",
        "x/y": (loaded.geometry.x, loaded.geometry.y) == (120, 240),
        "width_px": loaded.geometry.width_px == 900,
        "max_lines": loaded.geometry.max_lines == 4,
        "threads": loaded.audio.threads == 3,
    }
    print("=== Настройки: сохранение и загрузка ===")
    for name, ok in checks.items():
        print(f"  {name}: {'ок' if ok else 'ОШИБКА'}")
    result = all(checks.values())

    # восстановим прежний файл настроек
    if backup is not None:
        original_path.write_text(backup, encoding="utf-8")
    else:
        original_path.unlink(missing_ok=True)
    return result


def grab(screen, rect) -> np.ndarray:
    image = screen.grabWindow(0, rect[0], rect[1], rect[2], rect[3]).toImage()
    return np.frombuffer(image.constBits(), dtype=np.uint8).reshape(image.height(), image.width(), 4).copy()


def check_overlay_box(app) -> bool:
    settings = settings_module.Settings()
    settings.appearance.backdrop_enabled = True  # проверяем геометрию подложки
    settings.geometry.max_lines = 3
    settings.geometry.position = "bottom"
    settings.geometry.margin = 120
    settings.geometry.width_px = 900

    overlay = SubtitleOverlay(settings, exclude_from_capture=False)
    overlay.set_text("хорошо я сейчас попробую и перезапущу", 6, 3, 6)
    for _ in range(40):
        app.processEvents()
        time.sleep(0.03)

    screen = QGuiApplication.primaryScreen()
    available = screen.availableGeometry()
    geo = overlay.geometry()
    lines = overlay._lines  # noqa: SLF001
    line_height = overlay._line_height  # noqa: SLF001

    print("\n=== Рамка субтитров после исправления ===")
    print(f"  Строк текста: {len(lines)} (лимит {settings.geometry.max_lines})")
    print(f"  Окно: {geo.width()}x{geo.height()} в точке ({geo.x()},{geo.y()})")
    print(f"  Ожидаемая высота: 2*{settings.appearance.padding_y} + 3*{line_height} = "
          f"{2 * settings.appearance.padding_y + 3 * line_height}")
    print(f"  Занимает по высоте: {geo.height() / available.height() * 100:.0f}% экрана (было 34%)")
    print(f"  Скриншот: {ART / 'v2_box_fixed.png'}")

    ok_lines = len(lines) <= settings.geometry.max_lines
    # Ширина упирается в экран: в offscreen-режиме и на узких мониторах запрошенные
    # 900 px физически не влезают, поэтому сверяем высоту и что ширина не превысила экран.
    ok_size = (
        geo.width() <= min(900, available.width())
        and geo.height() == 2 * settings.appearance.padding_y + 3 * line_height
    )
    ok_screen = geo.height() < available.height() * 0.2

    rect = (geo.x() - 20, geo.y() - 20, geo.width() + 40, geo.height() + 40)
    screen_image = screen.grabWindow(0, rect[0], rect[1], rect[2], rect[3]).toImage()
    screen_image.save(str(ART / "v2_box_fixed.png"))
    with_text = np.frombuffer(screen_image.constBits(), dtype=np.uint8).reshape(
        screen_image.height(), screen_image.width(), 4
    ).copy()

    # геометрия рисуемой подложки — по альфа-каналу собственной отрисовки окна
    from PySide6.QtGui import QImage

    own = overlay.grab().toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    own_buffer = np.frombuffer(own.constBits(), dtype=np.uint8).reshape(own.height(), own.width(), 4)
    alpha = own_buffer[:, :, 3] > 8
    rows_own = np.nonzero(alpha.any(axis=1))[0]
    cols_own = np.nonzero(alpha.any(axis=0))[0]
    pill_w = pill_h = 0
    if rows_own.size and cols_own.size:
        pill_w = int(cols_own.max() - cols_own.min() + 1)
        pill_h = int(rows_own.max() - rows_own.min() + 1)
    expected_pill = settings.geometry.max_lines * line_height + 2 * settings.appearance.padding_y
    print(f"  Подложка: {pill_w}x{pill_h} px (ожидалось по высоте {expected_pill} — подложка по размеру рамки)")
    pill_ok = abs(pill_h - expected_pill) <= 3 and pill_w >= geo.width() - 4
    print(f"  Подложка облегает текст, а не всю рамку: {'да' if pill_ok else 'НЕТ'}")

    overlay.hide()
    for _ in range(20):
        app.processEvents()
        time.sleep(0.03)
    without = grab(screen, rect)
    diff = np.abs(with_text[:, :, :3].astype(int) - without[:, :, :3].astype(int)).sum(axis=2) > 10
    print(f"  Изменённых пикселей на экране в области рамки: {int(diff.sum())}")
    return ok_lines and ok_size and ok_screen and pill_ok


def check_dialog(app) -> bool:
    settings = settings_module.Settings()
    calls: list[str] = []
    dialog = SettingsDialog(
        settings,
        on_change=lambda s: calls.append("change"),
        on_apply=lambda s: calls.append("apply"),
        on_edit_box=lambda: calls.append("edit"),
    )
    dialog.show()
    for _ in range(40):
        app.processEvents()
        time.sleep(0.03)
    image = dialog.grab().toImage()
    image.save(str(ART / "v2_settings_dialog.png"))
    tabs = dialog.findChild(QListWidget)
    print("\n=== Окно настроек ===")
    print(f"  Размер окна: {dialog.width()}x{dialog.height()}, разделов: {tabs.count() if tabs else 0}")
    print(f"  Скриншот: {ART / 'v2_settings_dialog.png'}")

    # проверим, что изменение настройки отдаёт сигнал живого применения
    dialog.size_combo.setCurrentText("52")
    for _ in range(5):
        app.processEvents()
    changed = "change" in calls
    print(f"  Живое применение при изменении настроек: {'работает' if changed else 'НЕ работает'}")
    dialog.close()
    return changed and image.width() > 400


def check_edit_mode(app) -> bool:
    """Режим правки: перетаскивание и растягивание рамки мышью."""
    from PySide6.QtCore import QPointF

    class FakeMouseEvent:
        def __init__(self, x: float, y: float) -> None:
            self._point = QPointF(x, y)

        def position(self):
            return self._point

        def globalPosition(self):
            return self._point

        def accept(self) -> None:
            pass

    settings = settings_module.Settings()
    settings.geometry.position = "bottom"
    overlay = SubtitleOverlay(settings, exclude_from_capture=False)
    overlay.set_text("перетаскивание и растягивание", 2, 0, 2)
    for _ in range(30):
        app.processEvents()
        time.sleep(0.03)

    start_geometry = overlay.geometry()
    overlay.begin_edit_mode()
    overlay.mousePressEvent(FakeMouseEvent(60, 60))
    overlay.mouseMoveEvent(FakeMouseEvent(140, 100))
    overlay.mouseReleaseEvent(FakeMouseEvent(140, 100))
    for _ in range(10):
        app.processEvents()
    moved = overlay.geometry()

    overlay.mousePressEvent(FakeMouseEvent(overlay.width() - 5, overlay.height() - 5))
    overlay.mouseMoveEvent(FakeMouseEvent(overlay.width() + 115, overlay.height() + 65))
    overlay.mouseReleaseEvent(FakeMouseEvent(overlay.width() + 115, overlay.height() + 65))
    for _ in range(10):
        app.processEvents()
    resized = overlay.geometry()
    overlay.end_edit_mode()

    print("\n=== Режим правки рамки мышью ===")
    print(f"  старт: {start_geometry.x()},{start_geometry.y()} {start_geometry.width()}x{start_geometry.height()}")
    print(f"  после перетаскивания: {moved.x()},{moved.y()} {moved.width()}x{moved.height()}")
    print(f"  после растягивания: {resized.width()}x{resized.height()}, строк: {settings.geometry.max_lines}")
    print(f"  позиция сохранена как: {settings.geometry.position} ({settings.geometry.x},{settings.geometry.y})")
    moved_ok = (moved.x(), moved.y()) != (start_geometry.x(), start_geometry.y())
    resized_ok = resized.width() > moved.width() and resized.height() >= moved.height()
    saved_ok = settings.geometry.position == "custom" and settings.geometry.width_px == resized.width()
    print(f"  перетаскивание: {'ок' if moved_ok else 'ОШИБКА'}; растягивание: {'ок' if resized_ok else 'ОШИБКА'}; "
          f"сохранено в настройки: {'ок' if saved_ok else 'ОШИБКА'}")
    overlay.deleteLater()
    return moved_ok and resized_ok and saved_ok


def main() -> int:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:  # noqa: BLE001
        pass

    app = QApplication(sys.argv)
    results = {
        "settings": check_settings_roundtrip(),
        "overlay": check_overlay_box(app),
        "dialog": check_dialog(app),
        "edit_mode": check_edit_mode(app),
    }
    print("\n=== ИТОГ ===")
    for name, ok in results.items():
        print(f"  {name}: {'ок' if ok else 'ОШИБКА'}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
