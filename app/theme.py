"""Windows look and feel: bundled Roboto, dark palette when the system asks for it."""
from __future__ import annotations

import logging

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory

import paths

log = logging.getLogger(__name__)

def apply_ui_theme(app: QApplication) -> None:

    loaded = []
    for name in ("Roboto-Regular.ttf", "Roboto-Medium.ttf", "Roboto-Bold.ttf"):
        candidate = paths.fonts_dir() / name
        if candidate.exists():
            font_id = QFontDatabase.addApplicationFont(str(candidate))
            # addApplicationFont returns -1 when the file cannot be registered, and
            # QFont("Roboto").family() always answers "Roboto", so the old check could
            # never fail and the fallback never happened.
            if font_id < 0:
                log.warning("ui_font_load_failed path=%s", candidate)
            else:
                loaded.append(name)

    available = "Roboto" in QFontDatabase.families()
    font = QFont("Roboto")
    if not available:
        log.warning("ui_font_missing family='Roboto' loaded=%s action=use_system_font", loaded)
        font = QApplication.font()
    font.setPointSize(10)
    app.setFont(font)
    app.setStyleSheet(f"* {{ font-family: '{font.family()}'; }}")

    if "windows11" in QStyleFactory.keys():
        app.setStyle("windows11")

    dark = False
    try:
        import winreg

        path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            dark = winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
    except Exception:  # noqa: BLE001
        dark = False

    if dark:
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(31, 32, 35))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(240, 240, 240))
        palette.setColor(QPalette.ColorRole.Base, QColor(23, 24, 27))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(38, 38, 38))
        palette.setColor(QPalette.ColorRole.Text, QColor(240, 240, 240))
        palette.setColor(QPalette.ColorRole.Button, QColor(45, 45, 45))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(240, 240, 240))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(45, 45, 45))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor(240, 240, 240))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(91, 141, 245))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(150, 150, 150))
        app.setPalette(palette)
    log.debug("ui_theme dark=%s font=%r style=%r", dark, app.font().family(), app.style().objectName())
