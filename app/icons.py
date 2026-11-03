"""Application icon: a speech bubble with "Aa", two states."""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
import paths
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

log = logging.getLogger(__name__)

def _icon_path(captions_on: bool) -> Path:
    name = "icon.ico" if captions_on else "icon_off.ico"
    for folder in (paths.resource_dir(), Path(__file__).resolve().parent):
        candidate = folder / name
        if candidate.exists():
            return candidate
    return Path(__file__).resolve().parent / name


STATUS_COLORS = {"ok": "#3FBF85", "warn": "#E0B15C", "danger": "#E8736A"}
_SIZES = (16, 20, 24, 32, 48, 64, 128, 256)


def _compose(source: QPixmap, status: str, opacity: float) -> QPixmap:
    """Repaint one size: opacity plus the status dot in the lower right corner."""
    pixmap = QPixmap(source.size())
    pixmap.setDevicePixelRatio(source.devicePixelRatio())
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setOpacity(opacity)
    painter.drawPixmap(0, 0, source)
    colour = STATUS_COLORS.get(status)
    if colour:
        painter.setOpacity(1.0)
        side = float(source.width())
        dot = max(4.0, side * 0.34)
        ring = dot * 0.22
        x = side - dot - side * 0.02
        y = side - dot - side * 0.02
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#1F2023"))
        painter.drawEllipse(QRectF(x - ring, y - ring, dot + 2 * ring, dot + 2 * ring))
        painter.setBrush(QColor(colour))
        painter.drawEllipse(QRectF(x, y, dot, dot))
    painter.end()
    return pixmap


def make_icon(captions_on: bool = True, status: str = "", opacity: float = 1.0) -> QIcon:
    """Load a pre-rendered icon and add the status dot when there is one.

    The status used to be accepted and ignored, so nothing in the tray ever showed
    that recognition had stopped: the tooltip carried it, the icon did not.
    """
    path = _icon_path(captions_on)
    if path.exists():
        base = QIcon(str(path))
    else:
        # The packaging step guarantees both files are in the bundle and fails the
        # build without them, so a missing file here means someone deleted it from
        # an unpacked copy. Nothing is drawn in memory on purpose: a silently
        # redrawn icon would hide exactly the packaging bug this check exists for.
        log.warning("tray_icon_file_missing path=%s", path)
        base = QApplication.windowIcon()
    if opacity >= 0.995 and not STATUS_COLORS.get(status):
        return base
    composed = QIcon()
    for size in _SIZES:
        source = base.pixmap(size, size)
        if source.isNull():
            continue
        composed.addPixmap(_compose(source, status, opacity))
    return composed
