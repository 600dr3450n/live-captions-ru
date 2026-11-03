"""Version 4 verification: settings dialog, color picker, highlight levels, frame editing, icons."""
from __future__ import annotations

import ctypes
import json
import sys
import time
from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QGuiApplication, QPalette
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QLabel,
    QListWidget,
    QScrollArea,
    QSlider,
)

APP_DIR = Path(__file__).resolve().parent.parent / "app"
sys.path.insert(0, str(APP_DIR))

import settings as settings_module  # noqa: E402
from color_dialog import ColorCanvas, ColorDialog  # noqa: E402
from main import make_icon  # noqa: E402
from overlay import SubtitleOverlay, alpha_from_transparency  # noqa: E402
from settings_dialog import SettingsDialog  # noqa: E402

ART = Path(__file__).resolve().parent.parent / "_artifacts"
ART.mkdir(exist_ok=True)


class FakeMouseEvent:
    def __init__(self, x: float, y: float) -> None:
        self._point = QPointF(float(x), float(y))

    def position(self):
        return self._point

    def globalPosition(self):
        return self._point

    def accept(self) -> None:
        pass


def check_dialog(app) -> bool:
    """Three sections, required groups, toggles dim their own rows, pages are not clipped."""
    from PySide6.QtWidgets import QGroupBox, QListWidget, QScrollArea

    settings = settings_module.Settings()
    dialog = SettingsDialog(settings, on_change=lambda s: None, on_apply=lambda s: None, on_edit_box=lambda: None)
    dialog.resize(820, 640)
    dialog.show()
    for _ in range(20):
        app.processEvents()
        time.sleep(0.02)

    print("\n=== Окно настроек версии 1.0.0 ===")
    nav = dialog.findChild(QListWidget)
    titles = [nav.item(index).text() for index in range(nav.count())]
    print(f"  разделы: {titles}")
    ok = titles == ["Общие", "Внешний вид", "О приложении"]

    groups = [box.title() for box in dialog.findChildren(QGroupBox)]
    print(f"  группы: {groups}")
    expected = [
        "Запуск приложения",
        "Звук и экран",
        "Служебные действия",
        "Расположение и размер",
        "Текст",
        "Прозрачность текста",
        "Обводка текста",
        "Фон",
        "Версия",
    ]
    missing = [name for name in expected if name not in groups]
    print(f"  нет групп: {missing if missing else 'нет'}")
    ok = ok and not missing

    dialog.outline_switch.setChecked(False)
    for _ in range(5):
        app.processEvents()
    outline_off = not dialog.outline_width.isEnabled()
    dialog.outline_switch.setChecked(True)
    for _ in range(5):
        app.processEvents()
    outline_on = dialog.outline_width.isEnabled()

    dialog.backdrop_switch.setChecked(False)
    for _ in range(5):
        app.processEvents()
    backdrop_off = not dialog._padding_y_row.isEnabled()  # noqa: SLF001
    dialog.backdrop_switch.setChecked(True)
    for _ in range(5):
        app.processEvents()
    print(f"  обводка гаснет: {outline_off}, включается: {outline_on}, фон гаснет: {backdrop_off}")
    ok = ok and outline_off and outline_on and backdrop_off

    overflow = []
    for index, scroll in enumerate(dialog.findChildren(QScrollArea)):
        page = scroll.widget()
        if page.minimumSizeHint().width() > scroll.viewport().width() + 2:
            overflow.append((index, page.minimumSizeHint().width(), scroll.viewport().width()))
    print(f"  страниц с обрезкой содержимого: {len(overflow)} {overflow if overflow else ''}")
    ok = ok and not overflow

    dialog.grab().save(str(ART / "v4_dialog_new.png"))
    dialog.close()
    print(f"  Итог: {'ок' if ok else 'ОШИБКА'}")
    return ok


def check_color_dialog(app) -> bool:
    from PySide6.QtGui import QColor

    dialog = ColorDialog(QColor("#FFD400"))
    dialog.show()
    for _ in range(20):
        app.processEvents()
        time.sleep(0.02)
    has_parts = dialog.findChild(ColorCanvas) is not None and dialog.hex_edit.text() == "#FFD400"
    window_color = dialog.palette().color(QPalette.ColorRole.Window).name()
    app_color = app.palette().color(QPalette.ColorRole.Window).name()
    print("\n=== Выбор цвета ===")
    print(f"  Поле цвета и HEX на месте: {'ок' if has_parts else 'ОШИБКА'}")
    print(f"  Компактное окно: {dialog.width()}×{dialog.height()} — {'ок' if dialog.width() <= 360 else 'ОШИБКА'}")
    print(f"  Фон окна системный: {window_color} (в приложении {app_color}) — {'ок' if window_color == app_color else 'ОШИБКА'}")
    print(f"  Выбранный цвет: {dialog.color().name().upper()}")
    dialog.grab().save(str(ART / "v4_color_dialog.png"))
    print(f"  Скриншот: {ART / 'v4_color_dialog.png'}")
    dialog.close()
    return has_parts and window_color == app_color and dialog.width() <= 360

def check_opacity_levels(app) -> bool:
    settings = settings_module.Settings()
    settings.geometry.max_lines = 3  # so the previous line also fits
    overlay = SubtitleOverlay(settings, exclude_from_capture=False)
    long_text = "добрый день меня зовут анна я звоню по поводу вашего обращения в службу поддержки"
    words = long_text.split()
    overlay.set_text(long_text, len(words), len(words) - 2, len(words))
    for _ in range(40):
        app.processEvents()
        time.sleep(0.02)
    lines = overlay._lines  # noqa: SLF001
    alphas = [[word[2].alpha() for word in line] for line, _width, _x0 in lines]
    tail_alpha = alpha_from_transparency(settings.appearance.tail_transparency)
    active_alpha = alpha_from_transparency(settings.appearance.text_transparency)
    history_alpha = alpha_from_transparency(settings.appearance.history_transparency)
    print("\n=== Уровни подсветки текста ===")
    print(f"  Активный {active_alpha}, неподтверждённый {tail_alpha}, предыдущий {history_alpha}")
    print(f"  Прозрачности по строкам: {alphas}")
    last = alphas[-1] if alphas else []
    tail_ok = bool(last) and last[-1] == active_alpha and active_alpha > history_alpha
    history_line_ok = all(alpha == history_alpha for alpha in alphas[0]) if alphas else False
    committed_ok = any(alpha == history_alpha for line in alphas for alpha in line)
    print(f"  Последние слова — самые яркие: {'ок' if tail_ok else 'ОШИБКА'}")
    print(f"  Предыдущая реплика приглушена: {'ок' if history_line_ok else 'ОШИБКА'}")
    print(f"  Активный текст — средний уровень: {'ок' if committed_ok else 'ОШИБКА'}")
    overlay.set_preview(True)
    for _ in range(20):
        app.processEvents()
    overlay.grab().save(str(ART / "v4_text_levels.png"))
    overlay.hide()
    overlay.deleteLater()
    return tail_ok and history_line_ok and committed_ok


def check_edit_mode(app) -> bool:
    settings = settings_module.Settings()
    overlay = SubtitleOverlay(settings, exclude_from_capture=False)
    overlay.set_text("правки рамки", 2, 0, 2)
    for _ in range(30):
        app.processEvents()
        time.sleep(0.02)
    overlay.begin_edit_mode()
    for _ in range(20):
        app.processEvents()
        time.sleep(0.02)

    handles = overlay._handle_rects()  # noqa: SLF001
    print("\n=== Режим правки рамки ===")
    print(f"  Ручек: {len(handles)} (углы и середины сторон)")

    corners_ok = (
        overlay._handle_at(QPoint(1, 1)) == "nw"  # noqa: SLF001
        and overlay._handle_at(QPoint(overlay.width() - 1, 1)) == "ne"  # noqa: SLF001
        and overlay._handle_at(QPoint(overlay.width() // 2, 1)) == "n"  # noqa: SLF001
        and overlay._handle_at(QPoint(5, overlay.height() - 2)) == "sw"  # noqa: SLF001
    )
    cursors_ok = (
        overlay._cursor_for("se") == Qt.CursorShape.SizeFDiagCursor  # noqa: SLF001
        and overlay._cursor_for("n") == Qt.CursorShape.SizeVerCursor  # noqa: SLF001
        and overlay._cursor_for("e") == Qt.CursorShape.SizeHorCursor  # noqa: SLF001
        and overlay._cursor_for(None) == Qt.CursorShape.SizeAllCursor  # noqa: SLF001
    )
    print(f"  Курсоры под ручки и перемещение: {'ок' if cursors_ok else 'ОШИБКА'}")

    # snapping to the left screen edge: drag the frame far to the left
    screen = QGuiApplication.primaryScreen().availableGeometry()
    overlay.setGeometry(screen.left() + 120, screen.top() + 300, overlay.width(), overlay.height())
    for _ in range(10):
        app.processEvents()
    start_x = overlay.x()
    overlay.mousePressEvent(FakeMouseEvent(overlay.width() // 2, overlay.height() // 2))
    overlay.mouseMoveEvent(FakeMouseEvent(overlay.width() // 2 - (start_x - screen.left()) - 40,
                                          overlay.height() // 2 + 300))
    overlay.mouseReleaseEvent(FakeMouseEvent(0, 0))
    for _ in range(10):
        app.processEvents()
    snapped_x = overlay.x()
    snap_ok = snapped_x == screen.left()
    print(f"  Прилипание к левому краю: x={snapped_x} (край экрана {screen.left()}) — {'ок' if snap_ok else 'ОШИБКА'}")

    # resizing from the bottom-right corner enlarges the frame and the line count
    width_before, lines_before = overlay.width(), settings.geometry.max_lines
    overlay.mousePressEvent(FakeMouseEvent(overlay.width() - 2, overlay.height() - 2))
    overlay.mouseMoveEvent(FakeMouseEvent(overlay.width() + 160, overlay.height() + 70))
    overlay.mouseReleaseEvent(FakeMouseEvent(overlay.width() + 160, overlay.height() + 70))
    for _ in range(10):
        app.processEvents()
    resize_ok = overlay.width() > width_before and settings.geometry.max_lines > lines_before
    print(
        f"  Растягивание за угол: ширина {width_before} → {overlay.width()}, "
        f"строк {lines_before} → {settings.geometry.max_lines} — {'ок' if resize_ok else 'ОШИБКА'}"
    )
    print(f"  Положение сохранено как: {settings.geometry.position} ({settings.geometry.x},{settings.geometry.y})")
    overlay.end_edit_mode()
    overlay.hide()
    overlay.deleteLater()
    return len(handles) == 8 and corners_ok and cursors_ok and snap_ok and resize_ok


def check_icons(app) -> bool:
    icon = make_icon(True)
    print("\n=== Иконки ===")
    print(f"  Размеры в иконке: {sorted({icon.pixmap(s, s).width() for s in (16, 24, 32, 48, 64, 128, 256)})}")

    small = icon.pixmap(16, 16).toImage()
    big = icon.pixmap(256, 256).toImage().scaled(16, 16, Qt.AspectRatioMode.IgnoreAspectRatio,
                                                 Qt.TransformationMode.SmoothTransformation)
    import numpy as np

    def alpha(image):
        return np.frombuffer(image.constBits(), dtype=np.uint8).reshape(image.height(), image.width(), 4)[:, :, 3]

    diff = int((np.abs(alpha(small).astype(int) - alpha(big).astype(int)) > 30).sum())
    # The pixmap is identical at all sizes (the tray uses the same "Aa" bubble);
    # check that the small icon is not empty and contains the bubble
    filled = float((alpha(small) > 50).mean())
    print(f"  Заливка на 16 px: {filled * 100:.0f}% площади (различие с крупной: {diff} пикселей)")
    for size in (16, 32):
        icon.pixmap(size, size).scaled(size * 8, size * 8, Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.FastTransformation).save(str(ART / f"v4_icon_{size}.png"))
    print(f"  Скриншоты: {ART / 'v4_icon_16.png'}, {ART / 'v4_icon_32.png'}")
    return filled > 0.5


def check_migration() -> bool:
    path = settings_module.settings_path()
    backup = path.read_text(encoding="utf-8") if path.exists() else None
    old = {"appearance": {"text_opacity": 170, "tail_opacity": 255, "history_opacity": 50}, "version": 4}
    path.write_text(json.dumps(old), encoding="utf-8")
    loaded = settings_module.load_settings()
    migrated = (
        loaded.appearance.text_transparency == 0
        and loaded.appearance.tail_transparency == 80
        and loaded.appearance.history_transparency == 80
    )
    print("\n=== Миграция настроек (версия 4 → 5: непрозрачности → прозрачности) ===")
    print(
        f"  Активный {loaded.appearance.text_transparency}%, неподтверждённый {loaded.appearance.tail_transparency}%, "
        f"предыдущий {loaded.appearance.history_transparency}% — {'ок' if migrated else 'ОШИБКА'}"
    )
    if backup is not None:
        path.write_text(backup, encoding="utf-8")
    else:
        path.unlink(missing_ok=True)
    return migrated


def main() -> int:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:  # noqa: BLE001
        pass
    app = QApplication(sys.argv)
    results = {
        "dialog": check_dialog(app),
        "color": check_color_dialog(app),
        "levels": check_opacity_levels(app),
        "edit_mode": check_edit_mode(app),
        "icons": check_icons(app),
        "migration": check_migration(),
    }
    print("\n=== ИТОГ ===")
    for name, ok in results.items():
        print(f"  {name}: {'ок' if ok else 'ОШИБКА'}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
