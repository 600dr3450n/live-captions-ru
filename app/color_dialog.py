"""Compact colour picker: saturation/value field, hue strip, hex input."""
from __future__ import annotations

import re

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

HEX_RE = re.compile(r"^#?[0-9a-fA-F]{6}$")
INVALID_BORDER = "#E8736A"

class ColorCanvas(QWidget):

    changed = Signal(QColor)

    def __init__(self, color: QColor, parent=None) -> None:
        super().__init__(parent)
        self._hue = max(0, color.hsvHue()) if color.hsvHue() >= 0 else 0
        self._sat = color.hsvSaturation()
        self._val = color.value()
        self.setFixedSize(208, 226)
        self.setCursor(Qt.CursorShape.CrossCursor)

    # ------------------------------------------------------------------ API
    def color(self) -> QColor:
        return QColor.fromHsv(self._hue, self._sat, self._val)

    def set_color(self, color: QColor) -> None:
        self._hue = max(0, color.hsvHue()) if color.hsvHue() >= 0 else self._hue
        self._sat = color.hsvSaturation()
        self._val = color.value()
        self.update()

    def _square(self) -> QRectF:
        return QRectF(0, 0, self.width(), self.height() - 20)

    def _strip(self) -> QRectF:
        return QRectF(0, self.height() - 14, self.width(), 14)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        square = self._square()

        base = QColor.fromHsv(self._hue, 255, 255)
        painter.fillRect(square, base)
        white = QLinearGradient(square.topLeft(), square.topRight())
        white.setColorAt(0.0, QColor(255, 255, 255, 255))
        white.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillRect(square, white)
        black = QLinearGradient(square.topLeft(), square.bottomLeft())
        black.setColorAt(0.0, QColor(0, 0, 0, 0))
        black.setColorAt(1.0, QColor(0, 0, 0, 255))
        painter.fillRect(square, black)

        strip = self._strip()
        hue_gradient = QLinearGradient(strip.topLeft(), strip.topRight())
        for step in range(0, 361, 60):
            hue_gradient.setColorAt(step / 360.0, QColor.fromHsv(step % 360, 255, 255))
        painter.fillRect(strip, hue_gradient)

        marker_x = square.left() + square.width() * self._sat / 255.0
        marker_y = square.top() + square.height() * (1 - self._val / 255.0)
        painter.setPen(QPen(QColor(255, 255, 255, 230), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(marker_x, marker_y), 6, 6)
        painter.setPen(QPen(QColor(0, 0, 0, 160), 1))
        painter.drawEllipse(QPointF(marker_x, marker_y), 7, 7)

        strip_x = strip.left() + strip.width() * self._hue / 360.0
        painter.setPen(QPen(QColor(255, 255, 255, 240), 2))
        painter.drawRect(QRectF(strip_x - 3, strip.top(), 6, strip.height()))
        painter.end()

    def _update_from(self, point: QPointF) -> None:
        square = self._square()
        strip = self._strip()
        # Coordinates outside the widget are normal during a drag: grabMouse() keeps
        # sending moves after the cursor has left the canvas. The colour used to freeze
        # there, so dragging past an edge stopped at the last point inside it; now the
        # position is clamped to the nearest edge.
        # The 6 px gap between the square and the hue strip must still do nothing: it
        # used to fall into the first branch, so a click there clamped the value to the
        # bottom edge and silently picked black.
        if point.y() <= square.bottom():
            x = max(square.left(), min(square.right(), point.x()))
            y = max(square.top(), min(square.bottom(), point.y()))
            self._sat = int(round((x - square.left()) / square.width() * 255))
            self._val = int(round((1 - (y - square.top()) / square.height()) * 255))
        elif point.y() >= strip.top():
            x = max(strip.left(), min(strip.right(), point.x()))
            self._hue = int(round((x - strip.left()) / strip.width() * 359))
        else:
            return
        self.update()
        self.changed.emit(self.color())

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self.grabMouse()
        self._update_from(event.position())
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._update_from(event.position())
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self.mouseGrabber() is self:
            self.releaseMouse()
        event.accept()

class ColorDialog(QDialog):

    def __init__(self, color: QColor, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Цвет")
        self.setModal(True)
        self.setFixedWidth(232)
        self._color = QColor(color)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 10)
        layout.setSpacing(10)

        self.canvas = ColorCanvas(color, self)
        layout.addWidget(self.canvas)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.swatch = QLabel(self)
        self.swatch.setFixedSize(96, 26)
        row.addWidget(self.swatch)
        self.hex_edit = QLineEdit(self._color.name().upper(), self)
        self.hex_edit.setFixedWidth(96)
        self.hex_edit.setFixedHeight(26)
        self.hex_edit.setMaxLength(7)
        row.addWidget(self.hex_edit)
        row.addStretch(1)
        layout.addLayout(row)
        self.hint = QLabel("", self)
        self.hint.setStyleSheet(f"color: {INVALID_BORDER};")
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch(1)
        ok_button = QPushButton("ОК", self)
        ok_button.setDefault(True)
        ok_button.clicked.connect(self._accept_color)
        cancel = QPushButton("Отмена", self)
        cancel.clicked.connect(self.reject)
        buttons.addWidget(ok_button)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)

        self.canvas.changed.connect(self._on_canvas)
        self.hex_edit.textEdited.connect(self._on_hex)
        self._refresh()

    def _on_canvas(self, color: QColor) -> None:
        self._color = color
        self._refresh(sync_canvas=False)

    def _on_hex(self, text: str) -> None:
        value = text.strip()
        if HEX_RE.match(value):
            if not value.startswith("#"):
                value = "#" + value
            self._color = QColor(value)
            self.hex_edit.setStyleSheet("")
            self.hint.setText("")
            self._refresh(sync_canvas=True)

    def _refresh(self, sync_canvas: bool = False) -> None:
        if sync_canvas:
            self.canvas.set_color(self._color)
        name = self._color.name().upper()
        self.swatch.setStyleSheet(
            f"background: {name}; border: 1px solid #C6CAD3; border-radius: 4px;"
        )
        if self.hex_edit.text().upper() != name:
            self.hex_edit.blockSignals(True)
            self.hex_edit.setText(name)
            self.hex_edit.blockSignals(False)

    def _accept_color(self) -> None:
        text = self.hex_edit.text().strip()
        if not HEX_RE.match(text):
            # Closing with the previous colour while the field showed garbage gave the
            # user a colour they never typed and no hint that the input was rejected.
            self.hex_edit.setStyleSheet(f"border: 1px solid {INVALID_BORDER}; border-radius: 3px;")
            self.hex_edit.setFocus()
            self.hex_edit.selectAll()
            self.hint.setText("Цвет вводится как RRGGBB или #RRGGBB")
            return
        value = text if text.startswith("#") else "#" + text
        self._color = QColor(value)
        self.accept()

    # ------------------------------------------------------------------ API
    def color(self) -> QColor:
        return QColor(self._color)

def pick_color(parent, initial: str) -> str | None:
    dialog = ColorDialog(QColor(initial), parent)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        return dialog.color().name().upper()
    return None
