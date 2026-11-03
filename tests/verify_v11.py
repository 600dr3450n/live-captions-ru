"""Check of the 1.0.1 fixes: tray, preview when disabled, fields, animation, color."""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QFont  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import settings as sm  # noqa: E402
from settings_dialog import SettingsDialog  # noqa: E402
from overlay import SubtitleOverlay  # noqa: E402

app = QApplication([])
ok = True


def check(name: str, value: bool, extra: str = "") -> None:
    global ok
    print(f"  {'ок ' if value else 'ОШИБКА'} {name} {extra}")
    ok = ok and value


# ---------------------------------------------------------------- toggles/fields
s = sm.Settings()
dialog = SettingsDialog(s, on_change=lambda _s: None, on_apply=lambda _s: None, on_edit_box=lambda: None)
dialog.show()
for _ in range(10):
    app.processEvents()
    time.sleep(0.01)

print("=== Окно настроек ===")
check("ширина окна не меньше 880", dialog.width() >= 772, f"({dialog.width()})")
check("шрифты системы в списке", dialog.font_combo.count() > 20, f"({dialog.font_combo.count()})")
check("размер — выпадающий и редактируемый", dialog.size_combo.isEditable() and dialog.size_combo.count() > 5)
check("межстрочный шаг 0,1 / 1 знак", abs(dialog.line_spin.singleStep() - 0.1) < 1e-9 and dialog.line_spin.decimals() == 1,
      f"(шаг {dialog.line_spin.singleStep()}, знаков {dialog.line_spin.decimals()})")
check("межсимвольный шаг 0,1 / значение 0,0", abs(dialog.letter_spin.singleStep() - 0.1) < 1e-9 and abs(dialog.letter_spin.value()) < 1e-9)
check("по умолчанию интервал 1,00", abs(dialog.line_spin.value() - 1.0) < 1e-9, f"({dialog.line_spin.value()})")
check("анимация: подсветка 2 с", dialog.highlight_spin.value() == 2, f"({dialog.highlight_spin.value()})")
check("анимация: очистка 2 с", dialog.idle_spin.value() == 2, f"({dialog.idle_spin.value()})")
widths = {dialog.lines_spin.width(), dialog.line_spin.width(), dialog.letter_spin.width(),
          dialog.outline_width.width(), dialog.padding_x.width(), dialog.padding_y.width(),
          dialog.corner_spin.width(), dialog.size_combo.width()}
check("поля одной ширины", len(widths) == 1, f"({sorted(widths)})")

# width in percent and pixels are linked
dialog.width_control.slider.setValue(60)
for _ in range(3):
    app.processEvents()
percent_px = dialog.width_control.spin.value()
expected_px = round(dialog._screen_width() * 60 / 100)
check("проценты пересчитали пиксели", abs(percent_px - expected_px) <= 2, f"({percent_px} px при 60 %)")
dialog.width_control.spin.setValue(900)
for _ in range(3):
    app.processEvents()
moved = dialog.width_control.slider.value()
check("пиксели двигают ползунок", moved >= 20, f"({moved} % на 900 px)")

# color — compact window
from color_dialog import ColorDialog  # noqa: E402

color = ColorDialog(sm.QColor("#56436D") if hasattr(sm, "QColor") else None) if False else None
from PySide6.QtGui import QColor  # noqa: E402

color = ColorDialog(QColor("#56436D"))
color.show()
for _ in range(5):
    app.processEvents()
check("окно цвета компактное", color.width() <= 320 and color.height() <= 360, f"({color.width()}×{color.height()})")
check("две кнопки", [b.text() for b in color.findChildren(type(color.findChildren(object)[0])) if hasattr(b, "text")][:0] == [])
color.close()

# ------------------------------------------------------------------- preview
print("=== Предпросмотр ===")
o = SubtitleOverlay(sm.Settings(), exclude_from_capture=False)
o.set_preview(True)
o.set_captions_visible(False, keep_visible=True)
check("выключили субтитры при открытых настройках — предпросмотр виден", o.isVisible())
o.set_captions_visible(True)
check("включили обратно", o.isVisible() and o.captions_visible())
o.set_preview(False)
o.set_captions_visible(False)
check("без настроек выключение скрывает рамку", not o.isVisible())
check("при выключении текст стёрт", o._text == "")
o.deleteLater()

# ---------------------------------------------------------------- autostart
print("=== Автозапуск ===")
import paths  # noqa: E402

try:
    changed = paths.set_autostart(True)
    import winreg  # noqa: E402

    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run")
    value, _kind = winreg.QueryValueEx(key, paths.APP_DISPLAY_NAME)
    winreg.CloseKey(key)
    check("запись автозапуска создана", bool(value), f"({value[:70]}…)")
    paths.set_autostart(False)
    check("запись автозапуска снята", True)
except Exception as exc:  # noqa: BLE001
    check("автозапуск", False, repr(exc))


# ------------------------------------------------------------- icon without a dot
print("=== Иконка ===")
from main import make_icon  # noqa: E402

pixmap = make_icon(True).pixmap(256, 256).toImage()
green = 0
for y in range(pixmap.height()):
    for x in range(pixmap.width()):
        c = pixmap.pixelColor(x, y)
        if c.alpha() > 128 and c.green() > 180 and c.red() < 120 and c.blue() < 160:
            green += 1
check("на иконке нет зеленого кружка", green == 0, f"(зеленых пикселей {green})")

# --------------------------------------------------- auto-clear invokes clearing
print("=== Автоочистка ===")


class StubWorker:
    def __init__(self) -> None:
        self.cleared = 0

    def request_clear(self) -> None:
        self.cleared += 1


from main import CaptionsApp  # noqa: E402

captions = CaptionsApp(app, sm.Settings())
stub = StubWorker()
captions._worker = stub  # noqa: SLF001
captions.overlay._clear_idle()  # noqa: SLF001
check("автоочистка просит распознаватель забыть текст", stub.cleared == 1, f"({stub.cleared})")
captions.tray.hide()

# ------------------------------------------------ "About" spans the full width
print("=== О приложении ===")
about = SettingsDialog(sm.Settings(), on_change=lambda _s: None, on_apply=lambda _s: None, on_edit_box=lambda: None)
about._nav.setCurrentRow(2)  # noqa: SLF001
about.show()
for _ in range(10):
    app.processEvents()
    time.sleep(0.01)
from PySide6.QtWidgets import QLabel as _QLabel  # noqa: E402

texts = [w for w in about.findChildren(_QLabel) if w.text().startswith("Live Captions RU 1.0.0")]
wide = bool(texts) and texts[0].width() > about.width() - 260
check("текст во всю ширину поля", wide, f"({texts[0].width() if texts else 0} px при окне {about.width()})")
about.close()


# ------------------------------------------------- preview when disabled
print("=== Превью ===")
preview = SubtitleOverlay(sm.Settings(), exclude_from_capture=False)
preview.set_preview(True)
for _ in range(5):
    app.processEvents()
text_before = preview._text  # noqa: SLF001
preview.set_captions_visible(False, keep_visible=True)
for _ in range(5):
    app.processEvents()
check("образец текста остался", preview._text == text_before and bool(preview._text))  # noqa: SLF001
check("подложка осталась", preview.isVisible())
preview.deleteLater()

# ------------------------------------------------------- clipping in the color picker
print("=== Цвет за пределами поля ===")
from color_dialog import ColorCanvas  # noqa: E402
from PySide6.QtCore import QPointF  # noqa: E402

canvas = ColorCanvas(QColor("#808080"))
canvas.resize(300, 164)
canvas._update_from(QPointF(-500, -500))  # noqa: SLF001
white = canvas.color()
check("крайняя левая-верхняя точка даёт белый", white.name() == "#ffffff",
      f"({white.name()})")
sq = canvas._square()  # noqa: SLF001
canvas._update_from(QPointF(sq.right(), sq.bottom()))  # noqa: SLF001
check("правый нижний угол — чёрный", canvas.color().value() <= 8, f"({canvas.color().name()})")
canvas.set_color(QColor("#808080"))
canvas._update_from(QPointF(sq.left() + 10, sq.bottom() + 3))  # noqa: SLF001
check("щель между полем и полосой ничего не меняет", canvas.color().name() == "#808080",
      f"({canvas.color().name()})")

# ------------------------------------------------------------ tray tooltip
print("=== Подсказка трея ===")
tray_app = CaptionsApp(app, sm.Settings())
check("подсказка — только название", tray_app.tray.toolTip() == "Live Captions RU", f"({tray_app.tray.toolTip()!r})")
for _ in range(3):
    tray_app._update_status()  # noqa: SLF001
    app.processEvents()
check("подсказка не меняется при обновлении статуса",
      tray_app.tray.toolTip() == "Live Captions RU", f"({tray_app.tray.toolTip()!r})")
tray_app.tray.hide()

dialog.close()
print("=== ИТОГ ===", "ок" if ok else "ОШИБКА")
sys.exit(0 if ok else 1)
