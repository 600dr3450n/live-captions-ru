"""Russian texts for the standard Qt dialogs.

Qt keeps its own button captions ("OK", "Yes", "No", "Cancel") in the qtbase
translation, and that translation is not loaded by default. A Russian interface with
an English "Yes" in a confirmation is exactly the kind of detail users report, so the
app loads qtbase_ru and builds its own message boxes with explicit Russian buttons:
a missing .qm file in a future bundle then cannot bring English captions back.
"""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QLibraryInfo, QTranslator
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

log = logging.getLogger(__name__)

OK_TEXT = "ОК"
CANCEL_TEXT = "Отмена"

# Qt takes the translator by pointer, a local one is garbage collected right away.
_TRANSLATOR: QTranslator | None = None


def install_ui_translation(app: QApplication) -> bool:
    """Load Qt's Russian translation; return whether it was loaded.

    Without it the standard dialogs of the app (the tray menu is our own widgets, but
    message boxes are Qt's) show English captions. PyInstaller's PySide6 hook puts the
    .qm files into the bundle, so the translations folder is next to the package.
    """
    global _TRANSLATOR
    if _TRANSLATOR is not None:
        return True
    module_dir = Path(__file__).resolve().parent
    folders = [
        Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)),
        module_dir / "translations",
        module_dir.parent / "PySide6" / "translations",
    ]
    for folder in folders:
        if not folder or not Path(folder).is_dir():
            continue
        translator = QTranslator(app)
        if not translator.load("qtbase_ru", str(folder)):
            continue
        app.installTranslator(translator)
        _TRANSLATOR = translator
        log.info("ui_translation_loaded lang=ru path=%s", folder)
        return True
    log.warning("ui_translation_missing lang=ru action=explicit_russian_buttons")
    return False


def show_message(
    parent: QWidget | None,
    icon: QMessageBox.Icon,
    title: str,
    text: str,
    topmost: bool = False,
) -> None:
    """Plain message with one Russian button."""
    box = QMessageBox(parent)
    box.setIcon(icon)
    box.setWindowTitle(title)
    box.setText(text)
    box.addButton(OK_TEXT, QMessageBox.ButtonRole.AcceptRole)
    if topmost:
        # A plain box can open behind maximised windows and look like nothing happened.
        box.setWindowFlag(_topmost_flag(), True)
    box.exec()


def ask(
    parent: QWidget | None,
    title: str,
    text: str,
    ok_text: str = OK_TEXT,
) -> bool:
    """Question with Russian buttons: True when the user pressed OK."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle(title)
    box.setText(text)
    ok_button = box.addButton(ok_text, QMessageBox.ButtonRole.AcceptRole)
    box.addButton(CANCEL_TEXT, QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(ok_button)
    box.exec()
    return box.clickedButton() is ok_button


def _topmost_flag():
    from PySide6.QtCore import Qt

    return Qt.WindowType.WindowStaysOnTopHint
