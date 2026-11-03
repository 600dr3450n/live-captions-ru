"""Application paths, display name and logging setup."""
from __future__ import annotations

import logging
import os
import re
import sys
import tempfile
from logging.handlers import RotatingFileHandler
from pathlib import Path

APP_DIR_NAME = "LiveCaptionsRU"
APP_DISPLAY_NAME = "Live Captions RU"
APP_VERSION = "1.0.0"

log = logging.getLogger(__name__)


def app_data_dir() -> Path:
    """Directory for logs and settings.

    Falls back to the home directory when LOCALAPPDATA points somewhere unwritable:
    a broken environment variable must not stop the app from starting.
    """
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    path = Path(base) / APP_DIR_NAME
    try:
        path.mkdir(parents=True, exist_ok=True)
        return path
    except OSError as exc:
        log.warning("app_data_dir_failed path=%s error=%r action=fallback_to_home", path, exc)
    fallback = Path.home() / APP_DIR_NAME
    try:
        fallback.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        log.error("app_data_dir_fallback_failed path=%s error=%r action=use_path_as_is", fallback, exc)
    return fallback


def resource_dir() -> Path:
    """Bundled resources (PyInstaller) or project folder when run from sources."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent


def model_dir() -> Path:
    """Model location: next to the exe first (can be replaced), then bundled resources."""
    frozen = getattr(sys, "frozen", False)
    candidates: list[Path] = []
    if frozen:
        candidates.append(Path(sys.executable).resolve().parent / "models" / "t-one")
    candidates.append(resource_dir() / "models" / "t-one")

    for candidate in candidates:
        if (candidate / "model.onnx").exists() and (candidate / "tokens.txt").exists():
            return candidate
    raise FileNotFoundError(
        "T-one model not found (model.onnx and tokens.txt required). Check the models folder next to the app."
    )


def fonts_dir() -> Path:
    candidates = [resource_dir() / "fonts", Path(__file__).resolve().parent / "fonts"]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[0]


ROOT_MAIN = str(Path(__file__).resolve().parent / "main.py")


def set_autostart(enabled: bool) -> bool:
    import sys
    import winreg

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                command = f'"{sys.executable}"' if getattr(sys, "frozen", False) else f'"{sys.executable}" "{ROOT_MAIN}"'
                winreg.SetValueEx(key, APP_DISPLAY_NAME, 0, winreg.REG_SZ, command)
            else:
                try:
                    winreg.DeleteValue(key, APP_DISPLAY_NAME)
                except FileNotFoundError:
                    pass
        return True
    except Exception:  # noqa: BLE001
        return False


def autostart_enabled() -> bool | None:
    """Whether the Run key currently starts the app. None when it cannot be read."""
    try:
        import winreg
    except ImportError:
        return None
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_QUERY_VALUE) as key:
            winreg.QueryValueEx(key, APP_DISPLAY_NAME)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return None


def _fresh_log_on_new_version(log_path: Path) -> None:
    """Start a new log file when the version changes.

    The log is what users see through "Открыть журнал событий", so after an update
    it must not open on entries of the previous version. The old file is removed
    rather than rotated: RotatingFileHandler already keeps three history files, and
    a file from another build only confuses the report.
    """
    if not log_path.exists():
        return
    try:
        with log_path.open("r", encoding="utf-8", errors="replace") as handle:
            head = handle.read(4096)
    except OSError:
        return
    match = re.search(r"version=(\d+\.\d+\.\d+)", head)
    if match is None or match.group(1) == APP_VERSION:
        return
    try:
        log_path.unlink()
        for backup in log_path.parent.glob(log_path.name + ".*"):
            backup.unlink(missing_ok=True)
    except OSError:
        pass


def setup_logging(reset: bool = True) -> Path:
    """File log (the app runs without a console).

    `LCRU_DEBUG=1` in the environment raises the level to DEBUG, which is how phrase
    boundaries and gate decisions can be inspected on a user's machine without a
    rebuild: set the variable, start the app, read app.log.

    `reset=False` is used by a second copy that is about to exit: it must not delete the
    log of the instance that is still running.

    Never raises: an unwritable LOCALAPPDATA (read-only profile, disconnected drive)
    used to kill the windowed build before it could show a single message. The next
    candidate is the temp directory; if that fails too the app runs without a file log.
    """
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if os.environ.get("LCRU_DEBUG") else logging.INFO)
    root.handlers.clear()
    candidates = [
        app_data_dir() / "app.log",
        Path(tempfile.gettempdir()) / APP_DIR_NAME / "app.log",
    ]
    for log_path in candidates:
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            if reset:
                _fresh_log_on_new_version(log_path)
            handler = RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            log.warning("log_open_failed path=%s error=%r action=next_candidate", log_path, exc)
            continue
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root.addHandler(handler)
        return log_path
    log.error("log_open_failed path=%s error=all_candidates_unusable action=no_file_log", candidates[0])
    root.addHandler(logging.NullHandler())
    return candidates[0]
