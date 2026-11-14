"""Application icon: a speech bubble with "Aa", two states."""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt
import paths
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

log = logging.getLogger(__name__)

def _icon_path(captions_on: bool) -> Path:
    name = "icon.ico" if captions_on else "icon_off.ico"
    for folder in (paths.resource_dir(), Path(__file__).resolve().parent):
        candidate = folder / name
        if candidate.exists():
            return candidate
    return Path(__file__).resolve().parent / name


_SIZES = (16, 20, 24, 32, 48, 64, 128, 256)


def _compose(source: QPixmap, opacity: float) -> QPixmap:
    """Repaint one size at the given opacity."""
    pixmap = QPixmap(source.size())
    pixmap.setDevicePixelRatio(source.devicePixelRatio())
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setOpacity(opacity)
    painter.drawPixmap(0, 0, source)
    painter.end()
    return pixmap


def make_icon(captions_on: bool = True, opacity: float = 1.0) -> QIcon:
    """Load a pre-rendered icon; opacity only repaints already loaded pixmaps.

    The tray has exactly two looks, captions on and captions off. Nothing is drawn
    on top of them: no status dot, no colour code. A badge in the corner of a tray
    icon is not a contract anyone reads, and a colour that keeps changing behind the
    user's back reads as a defect rather than as a signal.
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
    if opacity >= 0.995:
        return base
    composed = QIcon()
    for size in _SIZES:
        source = base.pixmap(size, size)
        if source.isNull():
            continue
        composed.addPixmap(_compose(source, opacity))
    return composed
