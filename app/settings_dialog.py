"""Settings window with three sections and live preview."""
from __future__ import annotations

import logging

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices, QFont, QGuiApplication, QIntValidator
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFontComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

import paths
from settings import Settings
from presets import STYLES, apply_style
from style_tile import StyleCard
from widgets_ui import ColorRow, PercentAndPixels, PercentSlider, Switch

log = logging.getLogger(__name__)

NAV_WIDTH = 150
LABEL_WIDTH = 168
ROW_HEIGHT = 26
FIELD_WIDTH = 96
UNIT_COLOR = "#5B6170"


def make_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setMinimumWidth(LABEL_WIDTH)
    label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return label


class FormGrid(QGridLayout):

    def __init__(self) -> None:
        super().__init__()
        self.setHorizontalSpacing(10)
        self.setVerticalSpacing(6)
        self.setColumnStretch(1, 1)
        self._row = 0

    def add_row(self, label: str | None, *widgets: QWidget, stretch: bool = True) -> QWidget:
        if label is not None:
            self.addWidget(make_label(label), self._row, 0)
        holder = QWidget()
        box = QHBoxLayout(holder)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(8)
        for widget in widgets:
            box.addWidget(widget)
        box.addStretch(1) if stretch else box.addStretch(1)
        holder.setMinimumHeight(ROW_HEIGHT)
        self.addWidget(holder, self._row, 1)
        self._row += 1
        return holder

    def add_full(self, *widgets: QWidget) -> QWidget:
        holder = QWidget()
        box = QHBoxLayout(holder)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(8)
        for widget in widgets:
            box.addWidget(widget)
        box.addStretch(1)
        holder.setMinimumHeight(ROW_HEIGHT)
        self.addWidget(holder, self._row, 0, 1, 2)
        self._row += 1
        return holder


class SettingsDialog(QDialog):

    def __init__(self, settings: Settings, on_change, on_apply, on_edit_box) -> None:
        super().__init__()
        self._settings = settings
        self._on_change = on_change
        self._on_apply = on_apply
        self._on_edit_box = on_edit_box
        self._applied = False

        self.setWindowTitle(f"{paths.APP_DISPLAY_NAME} — Настройки")
        self.setModal(False)
        self.resize(772, 600)
        self.setMinimumSize(772, 600)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 10)
        outer.setSpacing(10)

        content = QHBoxLayout()
        content.setSpacing(12)
        self._nav = QListWidget()
        self._nav.setFixedWidth(NAV_WIDTH)
        self._nav.setFrameShape(QListWidget.Shape.NoFrame)
        self._nav.setSpacing(1)
        self._nav.setStyleSheet(
            "QListWidget::item { padding: 7px 10px; border-radius: 4px; }"
            "QListWidget::item:selected { background: #E9EEFB; color: #16181D; }"
        )
        self._pages = QStackedWidget()
        content.addWidget(self._nav)
        content.addWidget(self._pages, 1)
        outer.addLayout(content, 1)

        self._add_page("Общие", self._general_page())
        self._add_page("Внешний вид", self._appearance_page())
        self._add_page("О приложении", self._about_page())
        self._nav.currentRowChanged.connect(self._pages.setCurrentIndex)
        self._nav.setCurrentRow(0)
        self._refresh_style_selection()

        footer = QHBoxLayout()
        footer.addStretch(1)
        cancel_button = QPushButton("Отмена")
        cancel_button.clicked.connect(self.reject)
        ok_button = QPushButton("ОК")
        ok_button.setDefault(True)
        ok_button.clicked.connect(self.accept)
        footer.addWidget(ok_button)
        footer.addWidget(cancel_button)
        outer.addLayout(footer)

    def _add_page(self, title: str, content: QWidget) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        self._nav.addItem(QListWidgetItem(title))
        self._pages.addWidget(scroll)

    @staticmethod
    def _group(title: str) -> tuple[QGroupBox, FormGrid]:
        box = QGroupBox(title)
        grid = FormGrid()
        box.setLayout(grid)
        return box, grid

    @staticmethod
    def _field(widget: QWidget, unit: str) -> QWidget:
        holder = QWidget()
        box = QHBoxLayout(holder)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(6)
        box.addWidget(widget)
        label = QLabel(unit)
        label.setStyleSheet(f"color: {UNIT_COLOR};")
        box.addWidget(label)
        return holder

    def _spin(self, low: int, high: int, value: int) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(low, high)
        spin.setValue(int(value))
        spin.setFixedWidth(FIELD_WIDTH)
        spin.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        spin.setButtonSymbols(QSpinBox.ButtonSymbols.UpDownArrows)
        return spin

    def _dspin(self, low: float, high: float, value: float, step: float, decimals: int = 1) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(low, high)
        spin.setSingleStep(step)
        spin.setDecimals(decimals)
        spin.setValue(float(value))
        spin.setFixedWidth(FIELD_WIDTH)
        spin.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return spin

    def _general_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        box, grid = self._group("Запуск приложения")
        self.autostart = Switch(self._settings.behaviour.autostart)
        self.autostart.setToolTip("Добавляет программу в автозагрузку Windows")
        self.autostart.toggled.connect(lambda value: self._set("autostart", value, "behaviour"))
        grid.add_row("Запускать при входе в систему", self.autostart, stretch=False)
        self.start_visible = Switch(self._settings.behaviour.start_visible)
        self.start_visible.toggled.connect(lambda value: self._set("start_visible", value, "behaviour"))
        grid.add_row("Включать субтитры при запуске", self.start_visible, stretch=False)
        layout.addWidget(box)

        box, grid = self._group("Звук и экран")
        self.device_combo = QComboBox()
        default_name = ""
        try:
            import soundcard as sc

            for speaker in sc.all_speakers():
                self.device_combo.addItem(speaker.name, speaker.name)
            try:
                default_name = sc.default_speaker().name
            except Exception:  # noqa: BLE001
                default_name = ""
        except Exception as exc:  # noqa: BLE001
            log.warning("device_list_failed error=%r", exc)
        chosen = self._settings.audio.device or default_name
        self.device_combo.setCurrentIndex(max(0, self.device_combo.findData(chosen)))
        self.device_combo.setMinimumWidth(320)
        self.device_combo.currentIndexChanged.connect(
            lambda _index: self._set("device", self.device_combo.currentData(), "audio")
        )
        grid.add_row("Устройство вывода", self.device_combo)

        self.monitor_combo = QComboBox()
        from PySide6.QtGui import QGuiApplication

        for index, screen in enumerate(QGuiApplication.screens()):
            self.monitor_combo.addItem(f"{index + 1}: {screen.name()}", index)
        self.monitor_combo.setCurrentIndex(
            min(self._settings.geometry.monitor, max(0, self.monitor_combo.count() - 1))
        )
        # settings.json may name a monitor that is not connected (index 5 with one
        # screen). The list showed screen 1 while the model kept 5, and nothing told
        # the user the stored index was invalid.
        shown_monitor = self.monitor_combo.currentData()
        if shown_monitor is not None:
            self._settings.geometry.monitor = int(shown_monitor)
        self.monitor_combo.setMinimumWidth(320)
        self.monitor_combo.currentIndexChanged.connect(
            lambda _index: self._set("monitor", self.monitor_combo.currentData(), "geometry")
        )
        grid.add_row("Экран", self.monitor_combo)
        layout.addWidget(box)

        box, grid = self._group("Служебные действия")
        log_button = QPushButton("Открыть журнал событий")
        log_button.clicked.connect(self._open_log)
        reset_button = QPushButton("Сбросить настройки по умолчанию")
        reset_button.clicked.connect(self._reset_settings)
        grid.add_full(log_button, reset_button)
        layout.addWidget(box)
        layout.addStretch(1)
        return page

    def _appearance_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        appearance, geometry, behaviour = (
            self._settings.appearance,
            self._settings.geometry,
            self._settings.behaviour,
        )

        style_box_group = QGroupBox("Готовые стили оформления")
        style_box_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        style_layout = QVBoxLayout(style_box_group)
        style_layout.setContentsMargins(9, 6, 9, 9)
        style_layout.setSpacing(0)
        style_row = QWidget()
        style_row.setFixedHeight(124)
        style_box = QHBoxLayout(style_row)
        style_box.setContentsMargins(0, 0, 0, 0)
        style_box.setSpacing(12)
        self._style_cards: dict[str, StyleCard] = {}
        for style in STYLES:
            card = StyleCard(style, style_row)
            card.clicked.connect(self._apply_style)
            self._style_cards[style.key] = card
            style_box.addWidget(card)
        style_box.addStretch(1)
        style_layout.addWidget(style_row)
        self._style_cards["default"].set_selected(True)
        layout.addWidget(style_box_group)

        box, grid = self._group("Расположение и размер")
        self.position_combo = QComboBox()
        for title, value in (
            ("Снизу", "bottom"),
            ("По центру", "center"),
            ("Сверху", "top"),
            ("Свое", "custom"),
        ):
            self.position_combo.addItem(title, value)
        self.position_combo.setCurrentIndex(max(0, self.position_combo.findData(geometry.position)))
        self.position_combo.setFixedWidth(180)
        self.position_combo.currentIndexChanged.connect(
            lambda _index: self._set("position", self.position_combo.currentData(), "geometry")
        )
        grid.add_row("Расположение", self.position_combo)

        self.width_control = PercentAndPixels(
            geometry.width_percent,
            geometry.width_px or self._pixels_for(geometry.width_percent),
            lambda value: self._on_width_percent(value),
            lambda value: self._on_width_pixels(value),
        )
        grid.add_row("Размер по ширине", self.width_control)

        edit_button = QPushButton("Настроить область отображения субтитров")
        edit_button.clicked.connect(self._on_edit_box)
        grid.add_full(edit_button)
        layout.addWidget(box)

        box, grid = self._group("Анимация")
        self.highlight_spin = self._dspin(0.5, 10.0, behaviour.highlight_seconds, 0.5)
        self.highlight_spin.valueChanged.connect(
            lambda value: self._set("highlight_seconds", float(value), "behaviour")
        )
        grid.add_row("Держать слово ярким", self._field(self.highlight_spin, "с"), stretch=False)
        self.idle_spin = self._spin(0, 600, behaviour.idle_clear_sec)
        self.idle_spin.valueChanged.connect(lambda value: self._set("idle_clear_sec", value, "behaviour"))
        grid.add_row("Задержка очистки субтитров при паузе", self._field(self.idle_spin, "с"), stretch=False)
        layout.addWidget(box)

        box, grid = self._group("Текст")
        self.lines_spin = self._spin(1, 8, geometry.max_lines)
        self.lines_spin.valueChanged.connect(lambda value: self._set("max_lines", value, "geometry"))
        grid.add_row("Количество строк", self.lines_spin, stretch=False)

        self.font_combo = QFontComboBox()
        self.font_combo.setFixedWidth(180)
        self.font_combo.setCurrentFont(QFont(appearance.font_family))
        self.font_combo.currentFontChanged.connect(lambda font: self._set("font_family", font.family()))
        grid.add_row("Шрифт", self.font_combo)

        style_row = QWidget()
        style_box = QHBoxLayout(style_row)
        style_box.setContentsMargins(0, 0, 0, 0)
        style_box.setSpacing(14)
        self.bold_box = QCheckBox("Полужирный")
        self.bold_box.setChecked(appearance.bold)
        self.bold_box.toggled.connect(lambda value: self._set("bold", value))
        self.italic_box = QCheckBox("Курсив")
        self.italic_box.setChecked(appearance.italic)
        self.italic_box.toggled.connect(lambda value: self._set("italic", value))
        self.uppercase_box = QCheckBox("ЗАГЛАВНЫЕ")
        self.uppercase_box.setChecked(appearance.uppercase)
        self.uppercase_box.toggled.connect(lambda value: self._set("uppercase", value))
        for widget in (self.bold_box, self.italic_box, self.uppercase_box):
            style_box.addWidget(widget)
        style_box.addStretch(1)
        grid.add_row("Начертание", style_row)

        self.size_combo = QComboBox()
        self.size_combo.setEditable(True)
        self.size_combo.setFixedWidth(FIELD_WIDTH)
        for preset in range(12, 73, 2):
            self.size_combo.addItem(str(preset), preset)
        self.size_combo.setCurrentText(str(appearance.font_size_px))
        size_line = self.size_combo.lineEdit()
        size_line.setValidator(QIntValidator(10, 120, self))
        size_line.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.size_combo.currentTextChanged.connect(self._on_font_size)
        grid.add_row("Размер", self._field(self.size_combo, "px"), stretch=False)

        self.line_spin = self._dspin(0.8, 2.0, appearance.line_spacing, 0.1, decimals=1)
        self.line_spin.valueChanged.connect(lambda value: self._set("line_spacing", value))
        grid.add_row("Межстрочный интервал", self.line_spin, stretch=False)

        self.letter_spin = self._dspin(-3.0, 12.0, appearance.letter_spacing, 0.1)
        self.letter_spin.valueChanged.connect(lambda value: self._set("letter_spacing", value))
        grid.add_row("Межсимвольный интервал", self._field(self.letter_spin, "px"), stretch=False)

        self.align_combo = QComboBox()
        for title, value in (("Слева", "left"), ("По центру", "center"), ("Справа", "right")):
            self.align_combo.addItem(title, value)
        self.align_combo.setCurrentIndex(max(0, self.align_combo.findData(appearance.align)))
        self.align_combo.setFixedWidth(180)
        self.align_combo.currentIndexChanged.connect(
            lambda _index: self._set("align", self.align_combo.currentData())
        )
        grid.add_row("Выравнивание", self.align_combo)

        self.text_color = ColorRow(appearance.text_color, lambda value: self._set("text_color", value))
        grid.add_row("Цвет", self.text_color)
        layout.addWidget(box)

        box, grid = self._group("Прозрачность текста")
        self.history_opacity = PercentSlider(
            appearance.history_transparency, lambda value: self._set("history_transparency", value)
        )
        grid.add_row("Предыдущий", self.history_opacity)
        self.active_opacity = PercentSlider(
            appearance.text_transparency, lambda value: self._set("text_transparency", value)
        )
        grid.add_row("Активный", self.active_opacity)
        self.tail_opacity = PercentSlider(
            appearance.tail_transparency, lambda value: self._set("tail_transparency", value)
        )
        grid.add_row("Неподтвержденный", self.tail_opacity)
        layout.addWidget(box)

        box, grid = self._group("Обводка текста")
        self.outline_switch = Switch(appearance.outline_enabled)
        self.outline_switch.toggled.connect(self._on_outline_toggled)
        grid.add_row("Включить", self.outline_switch, stretch=False)
        self.outline_width = self._dspin(0.0, 12.0, appearance.outline_width, 0.1)
        self.outline_width.valueChanged.connect(lambda value: self._set("outline_width", value))
        self._outline_width_row = grid.add_row(
            "Толщина", self._field(self.outline_width, "px"), stretch=False
        )
        self.outline_color = ColorRow(appearance.outline_color, lambda value: self._set("outline_color", value))
        self._outline_color_row = grid.add_row("Цвет", self.outline_color)
        self.outline_opacity = PercentSlider(
            appearance.outline_transparency, lambda value: self._set("outline_transparency", value)
        )
        self._outline_opacity_row = grid.add_row("Прозрачность", self.outline_opacity)
        layout.addWidget(box)

        box, grid = self._group("Фон")
        self.backdrop_switch = Switch(appearance.backdrop_enabled)
        self.backdrop_switch.toggled.connect(self._on_backdrop_toggled)
        grid.add_row("Включить", self.backdrop_switch, stretch=False)
        self.padding_x = self._spin(0, 200, appearance.padding_x)
        self.padding_x.valueChanged.connect(lambda value: self._set("padding_x", value))
        self._padding_x_row = grid.add_row(
            "Отступ по горизонтали", self._field(self.padding_x, "px"), stretch=False
        )
        self.padding_y = self._spin(0, 200, appearance.padding_y)
        self.padding_y.valueChanged.connect(lambda value: self._set("padding_y", value))
        self._padding_y_row = grid.add_row(
            "Отступ по вертикали", self._field(self.padding_y, "px"), stretch=False
        )
        self.corner_spin = self._spin(0, 60, appearance.corner_radius)
        self.corner_spin.valueChanged.connect(lambda value: self._set("corner_radius", value))
        self._corner_row = grid.add_row("Скругление углов", self._field(self.corner_spin, "px"), stretch=False)
        self.backdrop_color = ColorRow(
            appearance.backdrop_color, lambda value: self._set("backdrop_color", value)
        )
        self._backdrop_color_row = grid.add_row("Цвет", self.backdrop_color)
        self.backdrop_opacity = PercentSlider(
            appearance.backdrop_transparency, lambda value: self._set("backdrop_transparency", value)
        )
        self._backdrop_opacity_row = grid.add_row("Прозрачность", self.backdrop_opacity)
        layout.addWidget(box)

        self._sync_switch_states()
        layout.addStretch(1)
        return page

    def _about_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        box, grid = self._group("Версия")
        text = QLabel(
            f"{paths.APP_DISPLAY_NAME} {paths.APP_VERSION} — Живые субтитры на русском языке. "
            "Распознавание речи без задержки в режиме реального времени. Работают без доступа к сети."
        )
        text.setWordWrap(True)
        text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        grid.addWidget(text, 0, 0, 1, 2)
        layout.addWidget(box)

        support_box, support_grid = self._group("Сообщение от автора")
        support_text = QLabel(
            "Здравствуйте! Я 600D R3450N — автор этой программы. "
            "Вы можете направлять мне свои отзывы и предложения по электронной почте: "
            '<a href="mailto:600dr3450n@gmail.com">600dr3450n@gmail.com</a>.<br><br>'
            "Данная программа полностью бесплатная. Если она вам понравилась, пожалуйста, поддержите ее развитие. Спасибо!"
        )
        support_text.setOpenExternalLinks(True)
        support_text.setTextFormat(Qt.TextFormat.RichText)
        support_text.setWordWrap(True)
        support_text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        support_grid.addWidget(support_text, 0, 0, 1, 2)
        support = QPushButton("Поддержать автора")
        support.clicked.connect(self._open_support)
        support_grid.addWidget(support, 1, 0, 1, 2, Qt.AlignmentFlag.AlignLeft)
        support_grid._row = 2
        layout.addWidget(support_box)

        layout.addStretch(1)
        return page

    def _set(self, name: str, value, section: str = "appearance") -> None:
        setattr(getattr(self._settings, section), name, value)
        self._settings.validated()
        # Any manual edit can move the values away from the preset: without this the
        # card kept its blue frame and the dialog claimed a style it no longer matched.
        if getattr(self, "_style_cards", None):
            self._refresh_style_selection()
        self._on_change(self._settings)

    def _target_screen(self):
        """The screen the box is configured for, not always the primary one.

        Percent to pixels and the ready-made styles used to be computed from the primary
        screen, so on a second monitor the number shown in settings and the position of a
        style both belonged to the wrong screen.
        """
        screens = QGuiApplication.screens()
        index = int(self._settings.geometry.monitor)
        if 0 <= index < len(screens):
            return screens[index]
        return QGuiApplication.primaryScreen()

    def _screen_width(self) -> int:
        """Width the overlay actually paints on: availableGeometry with avoid_taskbar."""
        screen = self._target_screen()
        if screen is None:
            return 1920
        if self._settings.geometry.avoid_taskbar:
            return int(screen.availableGeometry().width())
        return int(screen.geometry().width())

    def _pixels_for(self, percent: int) -> int:
        return max(1, round(self._screen_width() * int(percent) / 100))
        
    def _matching_style(self) -> str | None:
        """Return the preset that matches the current values, if any."""
        for style in STYLES:
            if all(
                getattr(self._settings.appearance, name) == value
                for name, value in style.appearance.items()
            ) and all(
                getattr(self._settings.geometry, name) == value
                for name, value in style.geometry.items()
            ):
                return style.key
        return None

    def _refresh_style_selection(self) -> None:
        matched = self._matching_style()
        for name, card in self._style_cards.items():
            card.set_selected(name == matched)

    def _apply_style(self, key: str) -> None:
        """Apply a ready-made style and refresh every control."""
        style = apply_style(self._settings, key)
        if style is None:
            return
        if key == "minimal":
            screen = self._target_screen()
            if screen is not None:
                line = round(style.appearance["font_size_px"] * style.appearance["line_spacing"])
                box_h = line * int(style.geometry["max_lines"]) + 2 * style.appearance["padding_y"]
                self._settings.geometry.x = 8
                self._settings.geometry.y = max(0, screen.geometry().height() - 24 - box_h // 2)
        self._on_change(self._settings)
        self._reload_widgets()

    def _on_font_size(self, text: str) -> None:
        digits = "".join(ch for ch in text if ch.isdigit())
        if not digits:
            return
        value = max(10, min(120, int(digits)))
        self._set("font_size_px", value)
        # Typing "9" left the field showing 9 while the model already held 10, and OK
        # saved 10 without ever re-reading the field.
        editor = self.size_combo.lineEdit()
        if editor is not None and editor.text() != str(value):
            editor.setText(str(value))

    def _on_width_percent(self, value: int) -> None:
        percent = max(20, min(100, int(value)))
        pixels = self._pixels_for(percent)
        self._set("width_px", 0, "geometry")
        self._set("width_percent", percent, "geometry")
        self.width_control.set_values(percent, pixels)

    def _on_width_pixels(self, value: int) -> None:
        pixels = max(0, int(value))
        if pixels <= 0:
            self._on_width_percent(self._settings.geometry.width_percent or 80)
            return
        percent = max(20, min(100, round(pixels * 100 / max(1, self._screen_width()))))
        self._set("width_px", pixels, "geometry")
        self._set("width_percent", percent, "geometry")
        self.width_control.set_values(percent, pixels)

    def _on_outline_toggled(self, enabled: bool) -> None:
        self._set("outline_enabled", enabled)
        self._sync_switch_states()

    def _on_backdrop_toggled(self, enabled: bool) -> None:
        self._set("backdrop_enabled", enabled)
        self._sync_switch_states()

    def _sync_switch_states(self) -> None:
        outline_on = self.outline_switch.isChecked()
        for row in (self._outline_width_row, self._outline_color_row, self._outline_opacity_row):
            row.setEnabled(outline_on)
        backdrop_on = self.backdrop_switch.isChecked()
        for row in (
            self._padding_x_row,
            self._padding_y_row,
            self._corner_row,
            self._backdrop_color_row,
            self._backdrop_opacity_row,
        ):
            row.setEnabled(backdrop_on)

    def _open_support(self) -> None:
        """Open the tip page in the default browser."""
        QDesktopServices.openUrl(QUrl("https://pay.cloudtips.ru/p/318e1bac"))

    def _open_log(self) -> None:
        """Open the log, and say so when there is nothing to open.

        The button used to do nothing at all on a first run (no app.log yet) and let
        OSError from startfile escape the Qt slot, so it looked broken.
        """
        log_path = paths.app_data_dir() / "app.log"
        if not log_path.exists():
            log.warning("open_log_skipped reason=missing path=%s", log_path)
            QMessageBox.information(
                self,
                "Журнал событий",
                "Журнал пока пуст: он появится после первого запуска распознавания.",
            )
            return
        try:
            import os

            os.startfile(str(log_path))  # noqa: S606
        except OSError as exc:
            log.error("open_log_failed path=%s error=%r", log_path, exc)
            QMessageBox.warning(
                self,
                "Журнал событий",
                f"Не удалось открыть журнал:\n{log_path}\n\n{exc}",
            )

    def _reset_settings(self) -> None:
        from settings import Settings

        # A single click used to throw away every setting, including the chosen device.
        answer = QMessageBox.question(
            self,
            "Сброс настроек",
            "Вернуть все настройки к значениям по умолчанию?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            log.info("settings_reset_cancelled")
            return
        defaults = Settings()
        self._settings.appearance = defaults.appearance
        self._settings.geometry = defaults.geometry
        self._settings.behaviour = defaults.behaviour
        self._settings.audio = defaults.audio
        self._settings.validated()
        self._on_change(self._settings)
        self._reload_widgets()
        # The combos are not part of _reload_widgets: after a reset the model went back
        # to "system default" while the list still showed the previous device.
        self._refresh_device_combo()
        self._refresh_monitor_combo()

    def _refresh_device_combo(self) -> None:
        """Rebuild the output device list and select what the model holds now."""
        chosen = self._settings.audio.device
        default_name = ""
        self.device_combo.blockSignals(True)
        try:
            self.device_combo.clear()
            try:
                import soundcard as sc

                for speaker in sc.all_speakers():
                    self.device_combo.addItem(speaker.name, speaker.name)
                try:
                    default_name = sc.default_speaker().name
                except Exception:  # noqa: BLE001
                    default_name = ""
            except Exception as exc:  # noqa: BLE001
                log.warning("device_list_failed error=%r", exc)
            self.device_combo.setCurrentIndex(max(0, self.device_combo.findData(chosen or default_name)))
        finally:
            self.device_combo.blockSignals(False)

    def _refresh_monitor_combo(self) -> None:
        """Rebuild the monitor list and select the stored index, clamped to it."""
        from PySide6.QtGui import QGuiApplication

        self.monitor_combo.blockSignals(True)
        try:
            self.monitor_combo.clear()
            for index, screen in enumerate(QGuiApplication.screens()):
                self.monitor_combo.addItem(f"{index + 1}: {screen.name()}", index)
            shown = min(self._settings.geometry.monitor, max(0, self.monitor_combo.count() - 1))
            self.monitor_combo.setCurrentIndex(max(0, shown))
            data = self.monitor_combo.currentData()
            if data is not None:
                self._settings.geometry.monitor = int(data)
        finally:
            self.monitor_combo.blockSignals(False)

    def current_page(self) -> int:
        return max(0, self._nav.currentRow())

    def show_page(self, index: int) -> None:
        self._nav.setCurrentRow(max(0, min(self._nav.count() - 1, int(index))))

    def reload_from_settings(self, settings: Settings) -> None:
        self._settings = settings
        self._reload_widgets()

    def _reload_widgets(self) -> None:
        appearance, geometry, behaviour = (
            self._settings.appearance,
            self._settings.geometry,
            self._settings.behaviour,
        )
        self.autostart.setChecked(behaviour.autostart)
        self.start_visible.setChecked(behaviour.start_visible)
        self.position_combo.setCurrentIndex(max(0, self.position_combo.findData(geometry.position)))
        self.width_control.set_values(
            geometry.width_percent,
            geometry.width_px or self._pixels_for(geometry.width_percent),
        )
        self.lines_spin.setValue(geometry.max_lines)
        self.bold_box.setChecked(appearance.bold)
        self.italic_box.setChecked(appearance.italic)
        self.uppercase_box.setChecked(appearance.uppercase)
        self.size_combo.setCurrentText(str(appearance.font_size_px))
        self.highlight_spin.setValue(float(behaviour.highlight_seconds))
        self.idle_spin.setValue(behaviour.idle_clear_sec)
        self.line_spin.setValue(appearance.line_spacing)
        self.letter_spin.setValue(appearance.letter_spacing)
        self.align_combo.setCurrentIndex(max(0, self.align_combo.findData(appearance.align)))
        self.text_color.set_color(appearance.text_color)
        self.history_opacity.set_value(appearance.history_transparency)
        self.active_opacity.set_value(appearance.text_transparency)
        self.tail_opacity.set_value(appearance.tail_transparency)
        self.outline_switch.setChecked(appearance.outline_enabled)
        self.outline_width.setValue(appearance.outline_width)
        self.outline_color.set_color(appearance.outline_color)
        self.outline_opacity.set_value(appearance.outline_transparency)
        self.backdrop_switch.setChecked(appearance.backdrop_enabled)
        self.padding_x.setValue(appearance.padding_x)
        self.padding_y.setValue(appearance.padding_y)
        self.corner_spin.setValue(appearance.corner_radius)
        self.backdrop_color.set_color(appearance.backdrop_color)
        self.backdrop_opacity.set_value(appearance.backdrop_transparency)
        # Font, device and monitor were missing from the reload: "Сбросить настройки
        # по умолчанию" changed the model while the lists still showed the old values,
        # and OK then compared them and restarted the pipeline for nothing.
        widgets = (self.font_combo, self.device_combo, self.monitor_combo)
        for widget in widgets:
            widget.blockSignals(True)
        try:
            self.font_combo.setCurrentFont(QFont(appearance.font_family))
            self.device_combo.setCurrentIndex(max(0, self.device_combo.findData(self._settings.audio.device)))
            monitor = min(int(geometry.monitor), max(0, self.monitor_combo.count() - 1))
            self.monitor_combo.setCurrentIndex(monitor)
            shown_monitor = self.monitor_combo.currentData()
            if shown_monitor is not None:
                self._settings.geometry.monitor = int(shown_monitor)
        finally:
            for widget in widgets:
                widget.blockSignals(False)
        self._sync_switch_states()
        self._refresh_style_selection()

    def accept(self) -> None:
        self._apply_and_close()

    def reject(self) -> None:
        """Cancel: the caller restores the snapshot it took when opening the dialog."""
        super().reject()

    def _apply_and_close(self) -> None:
        if not self._applied:
            self._applied = True
            self._on_apply(self._settings)
        super().accept()
