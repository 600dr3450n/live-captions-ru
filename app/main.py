"""Entry point: single instance, DPI, theme, tray application."""
from __future__ import annotations

import ctypes
import logging
import os
import sys

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

import paths
from app import CaptionsApp
from config import TAKEOVER_ARG, TAKEOVER_WAIT_SECONDS
from icons import make_icon
from settings import load_settings
from single_instance import already_running, wait_until_free
from theme import apply_ui_theme
from worker import RecognitionWorker

__all__ = [
    "CaptionsApp",
    "RecognitionWorker",
    "already_running",
    "apply_ui_theme",
    "main",
    "make_icon",
]

log = logging.getLogger("main")

def main() -> int:
    takeover = TAKEOVER_ARG in sys.argv
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor DPI
    except Exception:  # noqa: BLE001
        pass

    # The instance check runs before logging is opened, so a second copy cannot touch
    # the log file of the instance that is already running.
    if takeover:
        # Self relaunch: the previous copy is shutting down on purpose. Wait for the
        # mutex instead of trusting a fixed sleep, otherwise a slow shutdown leaves two
        # pipelines, two tray icons and two overlays on screen.
        ready = wait_until_free(TAKEOVER_WAIT_SECONDS)
        running = not ready
    else:
        ready = True
        running = already_running()

    try:
        log_path = paths.setup_logging(reset=not running)
    except Exception as exc:  # noqa: BLE001
        # setup_logging already falls back; this is the last line of defence so a
        # logging problem can never keep the window from appearing.
        log_path = paths.app_data_dir() / "app.log"
        log.error("setup_logging_failed error=%r action=continue_without_file_log", exc)
    log.info("app_start version=%s name=%r", paths.APP_VERSION, paths.APP_DISPLAY_NAME)
    log.info("log_file path=%s", log_path)
    log.debug("instance_check result=%s takeover=%s", "already_running" if running else "free", takeover)

    if running:
        log.info("instance_check result=already_running action=exit")
        app = QApplication(sys.argv)
        message = "Программа уже запущена — ищите значок в трее."
        if takeover:
            log.error("relaunch_takeover_timeout wait_s=%.0f action=exit", TAKEOVER_WAIT_SECONDS)
            message = (
                "Предыдущая копия не завершилась за "
                f"{TAKEOVER_WAIT_SECONDS:.0f} с. Закройте программу через значок в трее "
                "и запустите снова."
            )
        box = QMessageBox(
            QMessageBox.Icon.Information,
            paths.APP_DISPLAY_NAME,
            message,
        )
        # A plain information box can open behind maximised windows and look like nothing happened.
        box.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        box.exec()
        return 0

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName(paths.APP_DISPLAY_NAME)
    apply_ui_theme(app)
    app.setWindowIcon(make_icon(True))

    settings = load_settings()
    try:
        paths.model_dir()
    except FileNotFoundError as exc:
        log.error("model_missing error=%r", exc)
        if not takeover:
            QMessageBox.critical(None, paths.APP_DISPLAY_NAME, str(exc))
        return 2

    captions = CaptionsApp(app, settings)
    if not QSystemTrayIcon.isSystemTrayAvailable():
        log.warning("system_tray_unavailable")
    try:
        captions.start()
    except Exception as exc:  # noqa: BLE001
        log.error("startup_failed error=%r", exc)
        if not takeover:
            QMessageBox.critical(None, paths.APP_DISPLAY_NAME, f"Не удалось запустить распознавание:\n{exc}")
        return 3

    log.debug("app_ready")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
