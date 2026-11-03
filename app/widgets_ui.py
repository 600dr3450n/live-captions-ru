"""Reusable widgets for the settings window."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QWidget,
)

ACCENT = QColor("#2F6FED")


class Switch(QCheckBox):
    """Windows-style toggle: flips on press, keeps no pressed state and takes no focus."""

    def __init__(self, checked: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setChecked(checked)
        self.setFixedSize(40, 22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.toggled.connect(self.update)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.setChecked(not self.isChecked())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        event.accept()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.setChecked(not self.isChecked())
            event.accept()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        track = QRectF(1, 2, 38, 18)
        on = self.isChecked()
        painter.setPen(QPen(QColor("#C9C9C9") if not on else ACCENT, 1))
        painter.setBrush(ACCENT if on else QColor("#E8E8E8"))
        painter.drawRoundedRect(track, 9, 9)
        x = 23 if on else 5
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(QRectF(x, 5, 12, 12))
        painter.end()


class ColorRow(QWidget):

    PRESETS = (
        "#FFFFFF",
        "#C8C8C8",
        "#8C8C8C",
        "#000000",
        "#FFD84D",
        "#8FE3B0",
        "#9CC7FF",
        "#FFA8A8",
    )

    def __init__(self, color: str, on_change: Callable[[str], None]) -> None:
        super().__init__()
        self._color = color
        self._on_change = on_change
        self._buttons: list[QPushButton] = []
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        for preset in self.PRESETS:
            button = QPushButton()
            button.setFixedSize(18, 18)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setToolTip(preset)
            button.clicked.connect(lambda _checked=False, value=preset: self._pick(value))
            layout.addWidget(button)
            self._buttons.append(button)
        self._custom = QPushButton("Свой")
        self._custom.setFixedHeight(22)
        self._custom.setCursor(Qt.CursorShape.PointingHandCursor)
        self._custom.clicked.connect(self._choose)
        layout.addWidget(self._custom)
        layout.addStretch(1)
        self._refresh()

    def color(self) -> str:
        return self._color

    def set_color(self, color: str) -> None:
        self._color = color
        self._refresh()

    def _pick(self, color: str) -> None:
        self._color = color
        self._refresh()
        self._on_change(color)

    def _choose(self) -> None:
        from color_dialog import pick_color

        chosen = pick_color(self, self._color)
        if chosen:
            self._pick(chosen)

    def _refresh(self) -> None:
        for button, preset in zip(self._buttons, self.PRESETS):
            selected = preset.upper() == self._color.upper()
            border = "2px solid #2F6FED" if selected else "1px solid #9A9A9A"
            button.setStyleSheet(
                f"background:{preset}; border:{border}; border-radius:9px;"
            )


class PercentSlider(QWidget):

    def __init__(self, value: int, on_change: Callable[[int], None]) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.setSingleStep(5)
        self.slider.setPageStep(10)
        self.slider.setValue(max(0, min(100, int(value))))
        self.slider.setFixedWidth(180)
        self.label = QLabel(f"{int(value)} %")
        self.label.setFixedWidth(44)
        self.label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.label)

        def changed(new_value: int) -> None:
            self.label.setText(f"{new_value} %")
            on_change(new_value)

        self.slider.valueChanged.connect(changed)

    def set_value(self, value: int) -> None:
        blocked = self.slider.blockSignals(True)
        self.slider.setValue(max(0, min(100, int(value))))
        self.slider.blockSignals(blocked)
        self.label.setText(f"{int(value)} %")


class PercentAndPixels(QWidget):

    def __init__(
        self,
        percent: int,
        pixels: int,
        on_percent: Callable[[int], None],
        on_pixels: Callable[[int], None],
    ) -> None:
        super().__init__()
        from PySide6.QtWidgets import QSpinBox

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(20, 100)
        self.slider.setSingleStep(5)
        self.slider.setValue(max(20, min(100, int(percent))))
        self.slider.setFixedWidth(180)
        self.value = QLabel(f"{int(percent)} %")
        self.value.setFixedWidth(40)
        self.value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.spin = QSpinBox()
        # 0 means "follow the percent slider"; the old 200..4000 range silently
        # rewrote any smaller value that came from settings.json.
        self.spin.setRange(0, 4000)
        self.spin.setValue(max(0, int(pixels)))
        self.spin.setFixedWidth(96)
        self.spin.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        from PySide6.QtWidgets import QLabel as _QLabel

        unit = _QLabel("px")
        unit.setStyleSheet("color: #5B6170;")
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.value)
        layout.addWidget(self.spin)
        layout.addWidget(unit)

        def percent_changed(new_value: int) -> None:
            self.value.setText(f"{new_value} %")
            on_percent(new_value)

        self.slider.valueChanged.connect(percent_changed)
        self.spin.valueChanged.connect(on_pixels)

    def set_values(self, percent: int, pixels: int) -> None:
        blocked = self.slider.blockSignals(True)
        self.slider.setValue(max(20, min(100, int(percent))))
        self.slider.blockSignals(blocked)
        self.value.setText(f"{int(percent)} %")
        blocked = self.spin.blockSignals(True)
        self.spin.setValue(max(0, int(pixels)))
        self.spin.blockSignals(blocked)
