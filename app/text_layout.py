"""Text layout helpers: colours, outline drawing, word wrapping and truncation."""
from __future__ import annotations

import logging

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen

from settings import Appearance

log = logging.getLogger(__name__)

ELLIPSIS = "…"
MAX_ACTIVE_WORDS = 200  # more words in one phrase never fit on screen anyway

def alpha_from_transparency(transparency: int) -> int:
    value = max(0, min(100, int(transparency)))
    return max(0, min(255, round(255 * (100 - value) / 100)))



def qcolor(hex_value: str, alpha: int) -> QColor:
    color = QColor(hex_value)
    if not color.isValid():
        color = QColor("#FFFFFF")
    color.setAlpha(max(0, min(255, int(alpha))))
    return color


def draw_word(
    painter: QPainter,
    x: float,
    baseline: float,
    word: str,
    color: QColor,
    outline_color: QColor,
    outline_width: float,
    shadow_size: int,
    shadow_color: QColor,
) -> None:
    if shadow_size > 0 and shadow_color.alpha() > 0:
        painter.setPen(shadow_color)
        painter.drawText(QPointF(x + shadow_size, baseline + shadow_size), word)
    if outline_width > 0 and outline_color.alpha() > 0:
        path = QPainterPath()
        path.addText(QPointF(x, baseline), painter.font(), word)
        pen = QPen(outline_color)
        pen.setWidthF(outline_width * 2.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.strokePath(path, pen)
    painter.setPen(color)
    painter.drawText(QPointF(x, baseline), word)


def build_font(appearance: Appearance) -> QFont:
    font = QFont(appearance.font_family)
    font.setPixelSize(int(appearance.font_size_px))
    font.setWeight(QFont.Weight.Bold if appearance.bold else QFont.Weight.Normal)
    font.setItalic(bool(appearance.italic))
    if appearance.letter_spacing:
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, float(appearance.letter_spacing))
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return font


def split_long_word(word: str, metrics: QFontMetrics, max_width: int) -> list[str]:
    """Split a word that does not fit an empty line into pieces that do.

    A single long token (URL, hyphenated compound, a run of Latin letters) used to
    become a line wider than the plate and was clipped by the window edge, so part of
    the phrase was simply unreadable.
    """
    if max_width <= 0 or metrics.horizontalAdvance(word) <= max_width:
        return [word]
    pieces: list[str] = []
    current = ""
    for char in word:
        candidate = current + char
        if current and metrics.horizontalAdvance(candidate) > max_width:
            pieces.append(current)
            current = char
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces or [word]


def wrap_words(words: list[str], metrics: QFontMetrics, space: int, max_width: int) -> list[tuple[list[tuple[float, str]], int]]:
    """Break words into lines. Returns [(line_words_with_x, line_width), ...]."""
    # A zero or negative width would otherwise glue every word onto one endless line
    # that runs off the screen; one word per line is the sane degenerate case.
    max_width = max(1, int(max_width))
    lines: list[tuple[list[tuple[float, str]], int]] = []
    current: list[tuple[float, str]] = []
    x = 0.0
    for word in words:
        for index, piece in enumerate(split_long_word(word, metrics, max_width)):
            width = metrics.horizontalAdvance(piece)
            gap = float(space) if current and index == 0 else 0.0
            if current and x + gap + width > max_width:
                lines.append((current, int(x)))
                current, x = [], 0.0
                gap = 0.0
            x += gap
            current.append((x, piece))
            x += width
    if current:
        lines.append((current, int(x)))
    return lines


def wrap_flagged(
    words: list[tuple[str, bool]], metrics: QFontMetrics, space: int, max_width: int
) -> list[tuple[list[tuple[float, str, bool]], int]]:
    max_width = max(1, int(max_width))
    lines: list[tuple[list[tuple[float, str, bool]], int]] = []
    current: list[tuple[float, str, bool]] = []
    x = 0.0
    for word, flagged in words:
        for index, piece in enumerate(split_long_word(word, metrics, max_width)):
            width = metrics.horizontalAdvance(piece)
            gap = float(space) if current and index == 0 else 0.0
            if current and x + gap + width > max_width:
                lines.append((current, int(x)))
                current, x = [], 0.0
                gap = 0.0
            x += gap
            current.append((x, piece, flagged))
            x += width
    if current:
        lines.append((current, int(x)))
    return lines


def truncate_single_line(words: list[str], metrics: QFontMetrics, space: int, max_width: int) -> list[str]:
    total = sum(metrics.horizontalAdvance(word) for word in words) + space * max(0, len(words) - 1)
    if total <= max_width:
        return words
    kept: list[str] = []
    width = metrics.horizontalAdvance(ELLIPSIS)
    for word in reversed(words):
        extra = metrics.horizontalAdvance(word) + (space if kept else 0)
        if width + extra > max_width:
            break
        kept.insert(0, word)
        width += extra
    if not kept:
        return [ELLIPSIS]
    kept[0] = ELLIPSIS + kept[0]
    return kept
