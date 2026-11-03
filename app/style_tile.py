"""Tile widget that previews a style on a miniature desktop."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from presets import Style

DESKTOP = "#E8EDF5"
WINDOW = "#FBFCFE"
TASKBAR = "#F1F3F7"
ACCENT = "#2F6FED"
SAMPLE = "живые субтитры"


class StyleTile(QWidget):
    """A clickable picture of a caption style; the label sits below it."""

    clicked = Signal(str)

    def __init__(self, style: Style, parent=None) -> None:
        super().__init__(parent)
        self._style = style
        self._selected = False
        self.setFixedSize(176, 100)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(style.title)

    # ------------------------------------------------------------------ API
    def set_selected(self, selected: bool) -> None:
        if self._selected != selected:
            self._selected = selected
            self.update()

    def style_key(self) -> str:
        return self._style.key

    # ------------------------------------------------------------- painting
    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(DESKTOP))
        painter.drawRoundedRect(rect, 6, 6)

        # wallpaper: two large pastel blobs, close to the Windows 11 default
        painter.setBrush(QColor(205, 219, 242, 170))
        painter.drawEllipse(QRectF(-46, -30, 190, 150))
        painter.setBrush(QColor(219, 208, 238, 150))
        painter.drawEllipse(QRectF(self.width() - 96, 10, 190, 150))

        # taskbar, tall enough to stay readable in a 176x100 tile
        bar_height = 22
        taskbar = QRectF(1, self.height() - bar_height - 1, self.width() - 2, bar_height)
        painter.setBrush(QColor(TASKBAR))
        painter.drawRect(taskbar)

        # centred items with identical gaps: start button plus three pinned apps
        icon_size = 9
        gap = 6
        total = icon_size * 4 + gap * 3
        x = taskbar.center().x() - total / 2
        y = taskbar.center().y() - icon_size / 2
        painter.setBrush(QColor("#4C8BF5"))
        painter.drawRoundedRect(QRectF(x, y, icon_size, icon_size), 2, 2)
        painter.setBrush(QColor("#C3CAD8"))
        for index in range(3):
            painter.drawRoundedRect(QRectF(x + (icon_size + gap) * (index + 1), y, icon_size, icon_size), 2, 2)

        self._draw_caption(painter, taskbar)

        if self._selected:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(ACCENT), 2))
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 6, 6)
        painter.end()

    def _draw_caption(self, painter: QPainter, taskbar: QRectF) -> None:
        appearance = self._style.appearance
        geometry = self._style.geometry
        lines = int(geometry["max_lines"])
        scale = 0.30
        font_px = max(5, round(appearance["font_size_px"] * scale))
        padding_x = max(2, round(appearance["padding_x"] * scale))
        padding_y = max(1, round(appearance["padding_y"] * scale))
        line_height = max(7, round(font_px * appearance["line_spacing"] + 1))
        box_h = lines * line_height + 2 * padding_y
        box_w = int((self.width() - 16) * geometry["width_percent"] / 100)
        box_w = max(56, min(self.width() - 16, box_w))
        font_px = min(font_px, max(5, box_w // 13))

        if self._style.key == "minimal":
            box_x = 6
            box_y = taskbar.center().y() - box_h / 2
        elif self._style.key == "contrast":
            box_x = (self.width() - box_w) / 2
            box_y = taskbar.top() - box_h - 6
        else:
            box_x = (self.width() - box_w) / 2
            box_y = taskbar.top() - box_h - 8

        box = QRectF(box_x, box_y, box_w, box_h)
        if appearance["backdrop_enabled"]:
            color = QColor(appearance["backdrop_color"])
            color.setAlpha(max(0, min(255, round(255 * (100 - appearance["backdrop_transparency"]) / 100))))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            radius = max(0.0, appearance["corner_radius"] * scale)
            painter.drawRoundedRect(box, radius, radius)
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)

        if appearance["outline_enabled"] and appearance["outline_width"] > 0:
            outline = QColor(appearance["outline_color"])
            outline.setAlpha(round(255 * (100 - appearance["outline_transparency"]) / 100))
            painter.setPen(QPen(outline, max(1.0, appearance["outline_width"] * scale)))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(box, 2, 2)

        # thick bars stand for text lines: readable at tile size and honest about line count
        text_rect = box.adjusted(padding_x, padding_y, -padding_x, -padding_y)
        top = text_rect.top()
        bar_height = max(2.5, line_height * 0.42)
        for index in range(lines):
            ratio = 0.94 if index == 0 else 0.62
            bar_width = text_rect.width() * ratio
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(appearance["text_color"]))
            painter.drawRoundedRect(
                QRectF(
                    text_rect.left(),
                    top + index * line_height + (line_height - bar_height) / 2,
                    bar_width,
                    bar_height,
                ),
                bar_height / 2,
                bar_height / 2,
            )


    def mousePressEvent(self, event) -> None:  # noqa: N802
        self.clicked.emit(self._style.key)
        event.accept()


class StyleCard(QWidget):
    """Tile plus its caption, so the dialog can lay out three of them."""

    clicked = Signal(str)

    def __init__(self, style: Style, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.tile = StyleTile(style, self)
        self.tile.clicked.connect(self.clicked.emit)
        label = QLabel(style.title)
        label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.tile, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(label)

    def set_selected(self, selected: bool) -> None:
        self.tile.set_selected(selected)
