"""Version 5 verification: transparency, outline, letter case, backdrop, Cancel button, icon, text clearing."""
from __future__ import annotations

import ctypes
import json
import sys
import time
from pathlib import Path

import numpy as np
from PySide6.QtCore import QPointF, QRect, Qt
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QComboBox,
    QListWidget,
    QScrollArea,
    QSlider,
)

APP_DIR = Path(__file__).resolve().parent.parent / "app"
sys.path.insert(0, str(APP_DIR))

import settings as settings_module  # noqa: E402
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


def render_overlay(app, settings) -> np.ndarray:
    overlay = SubtitleOverlay(settings, exclude_from_capture=False)
    text = "проверка субтитров и еще слова"
    words = text.split()
    # the last word is still unconfirmed, the active one is the second-to-last
    overlay.set_text(text, len(words) - 1, len(words) - 3, len(words) - 1)
    for _ in range(30):
        app.processEvents()
        time.sleep(0.02)
    image = overlay.grab().toImage()
    data = np.frombuffer(image.constBits(), dtype=np.uint8).reshape(image.height(), image.width(), 4).copy()
    overlay.hide()
    overlay.deleteLater()
    return data


def ink(image) -> int:
    """Ink measure of an image: the sum of opacity across all pixels.

    Older sets measured "dense" pixels (alpha > 200); after switching to a
    real outline this stopped being sensitive: dimmed text yields no dense
    pixels at all, so the difference is invisible.
    """
    return int(image[:, :, 3].astype(np.int64).sum())


def check_transparency(app) -> bool:
    settings = settings_module.Settings()
    settings.geometry.max_lines = 3
    settings.appearance.backdrop_enabled = False  # measure text only
    settings.appearance.shadow = False
    settings.appearance.uppercase = False

    print("=== Прозрачность (100 % — не видно, 0 % — видно) ===")
    settings.appearance.text_transparency = 0
    visible = render_overlay(app, settings)
    settings.appearance.text_transparency = 100
    invisible = render_overlay(app, settings)
    diff = int((np.abs(visible[:, :, 3].astype(int) - invisible[:, :, 3].astype(int)) > 20).sum())
    active_ink = ink(visible) - ink(invisible)  # contribution of the active text (history stays)
    print(f"  Активный текст: 0 % → чернил {ink(visible)}, 100 % → чернил {ink(invisible)}, вклад текста {active_ink}")
    ok = diff > 200 and active_ink > 100_000

    settings.appearance.text_transparency = 0
    settings.appearance.tail_transparency = 0
    tail_bright = render_overlay(app, settings)
    settings.appearance.tail_transparency = 100
    tail_off = render_overlay(app, settings)
    tail_ink = ink(tail_bright) - ink(tail_off)
    print(
        f"  Неподтверждённое слово: 0 % → чернил {ink(tail_bright)}, 100 % → чернил {ink(tail_off)}, "
        f"вклад слова {tail_ink}"
    )
    ok = ok and tail_ink > 20_000

    stretched = alpha_from_transparency(0) == 255 and alpha_from_transparency(100) == 0
    print(f"  Перевод «прозрачность → альфа»: {alpha_from_transparency(0)} / {alpha_from_transparency(100)} — "
          f"{'ок' if stretched else 'ОШИБКА'}")
    return ok and stretched


def check_uppercase_and_outline(app) -> bool:
    settings = settings_module.Settings()
    settings.appearance.uppercase = False
    settings.appearance.outline_enabled = True

    print("\n=== Регистр и обводка в предпросмотре ===")
    lower = render_overlay(app, settings)
    settings.appearance.uppercase = True
    upper = render_overlay(app, settings)
    case_diff = int((np.abs(lower[:, :, 3].astype(int) - upper[:, :, 3].astype(int)) > 20).sum())
    print(f"  Смена регистра меняет картинку: {case_diff} пикселей — {'ок' if case_diff > 200 else 'ОШИБКА'}")

    settings.appearance.uppercase = False
    settings.appearance.outline_enabled = False
    no_outline = render_overlay(app, settings)
    outline_diff = int((np.abs(lower[:, :, 3].astype(int) - no_outline[:, :, 3].astype(int)) > 20).sum())
    print(f"  Выключение обводки меняет картинку: {outline_diff} пикселей — {'ок' if outline_diff > 50 else 'ОШИБКА'}")
    return case_diff > 200 and outline_diff > 50


def check_dialog(app) -> bool:
    settings = settings_module.Settings()
    dialog = SettingsDialog(settings, on_change=lambda s: None, on_apply=lambda s: None, on_edit_box=lambda: None)
    dialog.resize(820, 640)
    dialog.show()
    for _ in range(40):
        app.processEvents()
        time.sleep(0.02)

    print("\n=== Окно настроек: элементы и выравнивание ===")
    step_ok = abs(dialog.outline_width.singleStep() - 0.1) < 1e-9 and dialog.outline_width.decimals() == 1
    print(f"  Шаг обводки 0,1 px: {'ок' if step_ok else 'ОШИБКА'} (шаг {dialog.outline_width.singleStep()})")

    overflow = []
    for index, scroll in enumerate(dialog.findChildren(QScrollArea)):
        page = scroll.widget()
        needed = page.minimumSizeHint().width()
        available = scroll.viewport().width()
        if needed > available + 2:
            overflow.append((index, needed, available))
    print(f"  Страниц с обрезанным содержимым: {len(overflow)} {overflow if overflow else ''}")

    nav = dialog.findChild(QListWidget)
    titles = [nav.item(i).text() for i in range(nav.count())]
    print(f"  Разделы: {titles}")
    for row in range(nav.count()):
        nav.setCurrentRow(row)
        for _ in range(6):
            app.processEvents()
    dialog.close()
    return step_ok and not overflow


def check_backdrop_equals_frame(app) -> bool:
    settings = settings_module.Settings()
    settings.appearance.backdrop_enabled = True
    settings.appearance.backdrop_transparency = 0
    settings.geometry.width_px = 800
    settings.geometry.max_lines = 3
    data = render_overlay(app, settings)
    alpha = data[:, :, 3]
    rows = np.nonzero((alpha > 20).any(axis=1))[0]
    cols = np.nonzero((alpha > 20).any(axis=0))[0]
    filled_width = int(cols.max() - cols.min() + 1) if cols.size else 0
    filled_height = int(rows.max() - rows.min() + 1) if rows.size else 0
    print("\n=== Подложка занимает всю рамку ===")
    print(f"  Рамка 800×{settings.geometry.max_lines} строки, закрашено: {filled_width}×{filled_height}")
    ok = filled_width >= 795
    print(f"  {'ок' if ok else 'ОШИБКА'}")
    return ok


def check_edit_cancel(app) -> bool:
    settings = settings_module.Settings()
    overlay = SubtitleOverlay(settings, exclude_from_capture=False)
    overlay.set_text("кнопки отмены", 1, 0, 1)
    for _ in range(20):
        app.processEvents()
        time.sleep(0.02)
    original = QRect(overlay.geometry())
    overlay.begin_edit_mode()
    for _ in range(10):
        app.processEvents()

    overlay.mousePressEvent(FakeMouseEvent(overlay.width() // 2, overlay.height() // 2))
    overlay.mouseMoveEvent(FakeMouseEvent(overlay.width() // 2 + 150, overlay.height() // 2 - 120))
    overlay.mouseReleaseEvent(FakeMouseEvent(0, 0))
    for _ in range(10):
        app.processEvents()
    moved = QRect(overlay.geometry())

    cancel_rect = overlay._cancel_rect()  # noqa: SLF001
    overlay.mousePressEvent(FakeMouseEvent(cancel_rect.center().x(), cancel_rect.center().y()))
    for _ in range(10):
        app.processEvents()
    cancelled = QRect(overlay.geometry())
    settings_ok = settings.geometry.position != "custom" or settings.geometry.width_px == overlay.width()

    print("\n=== Кнопки «Отмена» и «Готово» ===")
    print(f"  До правки: {original.x()},{original.y()} {original.width()}x{original.height()}")
    print(f"  После перетаскивания: {moved.x()},{moved.y()}")
    print(f"  После «Отмена»: {cancelled.x()},{cancelled.y()} — {'ок' if cancelled.topLeft() == original.topLeft() else 'ОШИБКА'}")
    print(f"  Настройки не изменены: {'ок' if settings.geometry.position == 'custom' or settings.geometry.max_lines == 2 else 'проверьте'}")

    # Done button — changes are saved
    overlay.begin_edit_mode()
    for _ in range(10):
        app.processEvents()
    overlay.mousePressEvent(FakeMouseEvent(overlay.width() // 2, overlay.height() // 2))
    overlay.mouseMoveEvent(FakeMouseEvent(overlay.width() // 2 + 60, overlay.height() // 2 + 40))
    overlay.mouseReleaseEvent(FakeMouseEvent(0, 0))
    done_rect = overlay._done_rect()  # noqa: SLF001
    overlay.mousePressEvent(FakeMouseEvent(done_rect.center().x(), done_rect.center().y()))
    for _ in range(10):
        app.processEvents()
    saved_ok = settings.geometry.position == "custom"
    print(f"  После «Готово» положение сохранено: {'ок' if saved_ok else 'ОШИБКА'} ({settings.geometry.x},{settings.geometry.y})")
    overlay.hide()
    overlay.deleteLater()
    return cancelled.topLeft() == original.topLeft() and saved_ok


def check_icons(app) -> bool:
    icon = make_icon(True)
    images = {}
    for size in (16, 24, 32, 64):
        image = icon.pixmap(size, size).toImage()
        images[size] = np.frombuffer(image.constBits(), dtype=np.uint8).reshape(
            image.height(), image.width(), 4
        )[:, :, 3].astype(float) / 255.0
    small = images[16]
    big = images[64][::4, ::4][:16, :16]
    correlation = float(
        np.corrcoef(small.reshape(-1), big.reshape(-1))[0, 1]
    )
    filled = float((small > 0.2).mean())
    print("\n=== Иконка («Aa» на всех размерах, крупнее) ===")
    print(f"  Заливка на 16 px: {filled * 100:.0f}% площади")
    print(f"  Совпадение рисунка 16 px и 64 px (один и тот же дизайн): {correlation:.2f}")
    icon.pixmap(16, 16).scaled(128, 128, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.FastTransformation).save(str(ART / "v5_icon_16.png"))
    print(f"  Скриншот: {ART / 'v5_icon_16.png'}")
    return filled > 0.5 and correlation > 0.6


def check_worker_clear() -> bool:
    import queue
    from types import SimpleNamespace

    import main as app_main

    class FakeRecognizer:
        def __init__(self) -> None:
            self.index = 0

        def create_stream(self):
            return object()

        def feed(self, stream, samples, rate) -> str:
            self.index += 1
            return "старый текст из прошлого разговора" if self.index < 4 else "новый текст"

        def is_endpoint(self, stream) -> bool:
            return False

        def reset(self, stream) -> None:
            pass

        def finish(self, stream) -> str:
            return ""

    states: list[tuple] = []
    audio: "queue.Queue" = queue.Queue()
    worker = app_main.RecognitionWorker(FakeRecognizer(), audio, lambda *args: states.append(args), lambda: False)
    worker.start()
    chunk = SimpleNamespace(samples=np.zeros(960, dtype=np.float32), rate=48000)
    for _ in range(5):
        audio.put(chunk)
        time.sleep(0.12)
    worker.request_clear()
    for _ in range(6):
        audio.put(chunk)
        time.sleep(0.12)
    time.sleep(0.3)
    worker.stop()
    worker.join(timeout=2.0)

    texts = [state[1] for state in states]
    non_empty = [text for text in texts if text]
    cleaned = bool(non_empty) and "старый" not in non_empty[-1]
    print("\n=== Очистка старого текста при выходе из настроек ===")
    print(f"  Состояния после очистки: {texts}")
    print(f"  Последний непустой текст: {non_empty[-1] if non_empty else '—'}")
    print(f"  Старый текст больше не показывается: {'ок' if cleaned else 'ОШИБКА'}")
    return cleaned


def check_migration() -> bool:
    path = settings_module.settings_path()
    backup = path.read_text(encoding="utf-8") if path.exists() else None
    old = {
        "appearance": {"text_opacity": 170, "tail_opacity": 255, "history_opacity": 50, "backdrop_opacity": 115},
        "version": 4,
    }
    path.write_text(json.dumps(old), encoding="utf-8")
    loaded = settings_module.load_settings()
    migrated = (
        loaded.appearance.text_transparency == 0
        and loaded.appearance.tail_transparency == 80
        and loaded.appearance.history_transparency == 80
        and loaded.appearance.backdrop_transparency == 55
    )
    print("\n=== Миграция настроек (версия 4 → 5) ===")
    print(
        f"  Непрозрачности → прозрачности: активный {loaded.appearance.text_transparency}%, "
        f"неподтверждённый {loaded.appearance.tail_transparency}%, "
        f"предыдущий {loaded.appearance.history_transparency}%, "
        f"подложка {loaded.appearance.backdrop_transparency}% — {'ок' if migrated else 'ОШИБКА'}"
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
        "transparency": check_transparency(app),
        "case_and_outline": check_uppercase_and_outline(app),
        "dialog": check_dialog(app),
        "backdrop": check_backdrop_equals_frame(app),
        "edit_cancel": check_edit_cancel(app),
        "icons": check_icons(app),
        "worker_clear": check_worker_clear(),
        "migration": check_migration(),
    }
    print("\n=== ИТОГ ===")
    for name, ok in results.items():
        print(f"  {name}: {'ок' if ok else 'ОШИБКА'}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
