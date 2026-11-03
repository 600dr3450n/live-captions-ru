"""Application settings: defaults, validation, JSON persistence."""
from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from paths import app_data_dir, autostart_enabled

log = logging.getLogger(__name__)

SETTINGS_VERSION = 9
SETTINGS_FILE = "settings.json"


def settings_path() -> Path:
    return app_data_dir() / SETTINGS_FILE


# Smallest width the settings field can show next to the percent slider.
MIN_WIDTH_PX = 200


def _clamp(value, low, high, fallback):
    try:
        number = type(fallback)(value)
    except (TypeError, ValueError, OverflowError):
        # OverflowError covers settings.json values like 1e400, which json reads as
        # inf: int(inf) raises and used to send the whole file to quarantine.
        return fallback
    return max(low, min(high, number))


def _num(value, cast, low, high, fallback):
    """Silent coercion: a stale or edited settings.json must never stop the app.

    Bad values fall back to the default and get clamped to the allowed range, with
    no log chatter per field. Only an unparsable file gets a warning.
    """
    try:
        number = cast(value)
    except (TypeError, ValueError, OverflowError):
        return fallback
    return max(low, min(high, number))


@dataclass
class Appearance:

    font_family: str = "Roboto"
    font_size_px: int = 24
    bold: bool = True
    italic: bool = False
    line_spacing: float = 1.0
    letter_spacing: float = 0.0
    text_color: str = "#FFFFFF"
    text_transparency: int = 0
    outline_enabled: bool = True
    outline_color: str = "#000000"
    outline_transparency: int = 20
    outline_width: float = 1.0
    tail_transparency: int = 40
    history_transparency: int = 40
    backdrop_enabled: bool = True
    backdrop_color: str = "#000000"
    backdrop_transparency: int = 40
    corner_radius: int = 6
    padding_x: int = 12
    padding_y: int = 12
    shadow: bool = False
    shadow_size: int = 3
    align: str = "left"
    uppercase: bool = True

    def validated(self) -> "Appearance":
        self.font_size_px = _clamp(self.font_size_px, 10, 120, 28)
        self.line_spacing = _num(self.line_spacing, float, 0.8, 2.0, 1.0)
        self.letter_spacing = _num(self.letter_spacing, float, -3.0, 12.0, 0.0)
        self.text_transparency = _clamp(self.text_transparency, 0, 100, 80)
        self.outline_transparency = _clamp(self.outline_transparency, 0, 100, 0)
        self.outline_width = _num(self.outline_width, float, 0.0, 12.0, 0.0)
        self.tail_transparency = _clamp(self.tail_transparency, 0, 100, 0)
        self.history_transparency = _clamp(self.history_transparency, 0, 100, 80)
        self.backdrop_transparency = _clamp(self.backdrop_transparency, 0, 100, 55)
        self.corner_radius = _clamp(self.corner_radius, 0, 60, 18)
        self.padding_x = _clamp(self.padding_x, 0, 200, 26)
        self.padding_y = _clamp(self.padding_y, 0, 200, 16)
        self.shadow_size = _clamp(self.shadow_size, 1, 30, 4)
        if self.align not in ("left", "center", "right"):
            self.align = "center"
        if not isinstance(self.font_family, str) or not self.font_family.strip():
            self.font_family = "Roboto"
        for name, fallback in (("text_color", "#FFFFFF"), ("outline_color", "#000000"), ("backdrop_color", "#000000")):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.startswith("#") or len(value) not in (7, 9):
                setattr(self, name, fallback)
        for name in ("bold", "italic", "outline_enabled", "backdrop_enabled", "shadow", "uppercase"):
            if not isinstance(getattr(self, name), bool):
                setattr(self, name, bool(getattr(self, name)))
        return self


@dataclass
class Geometry:
    """Subtitle box position and size."""

    position: str = "bottom"  # bottom | top | center | custom
    x: int = 440
    y: int = 906
    margin: int = 40
    monitor: int = 0
    width_percent: int = 40
    width_px: int = 0  # > 0 overrides percent
    max_lines: int = 2
    avoid_taskbar: bool = True

    def validated(self) -> "Geometry":
        if self.position not in ("bottom", "top", "center", "custom"):
            self.position = "bottom"
        self.margin = _clamp(self.margin, 0, 600, 150)
        self.monitor = _clamp(self.monitor, 0, 8, 0)
        self.width_percent = _clamp(self.width_percent, 20, 100, 62)
        self.width_px = _clamp(self.width_px, 0, 4000, 0)
        if 0 < self.width_px < MIN_WIDTH_PX:
            # The field shows 0 ("по проценту") or at least MIN_WIDTH_PX, so anything
            # in between was displayed as one value and saved as another.
            self.width_px = MIN_WIDTH_PX
        self.max_lines = _clamp(self.max_lines, 1, 8, 3)
        self.x = _clamp(self.x, -100, 10000, -1)
        self.y = _clamp(self.y, -100, 10000, -1)
        if not isinstance(self.avoid_taskbar, bool):
            self.avoid_taskbar = bool(self.avoid_taskbar)
        return self


@dataclass
class Behaviour:
    """How many lines to show and when to clear them."""

    idle_clear_sec: int = 2  # 0 = never clear
    highlight_seconds: float = 2.0
    autostart: bool = False
    start_visible: bool = True

    def validated(self) -> "Behaviour":
        self.idle_clear_sec = _clamp(self.idle_clear_sec, 0, 600, 2)
        self.highlight_seconds = _num(self.highlight_seconds, float, 0.5, 10.0, 2.0)
        for name in ("autostart", "start_visible"):
            if not isinstance(getattr(self, name), bool):
                setattr(self, name, bool(getattr(self, name)))
        return self


@dataclass
class Audio:
    """Capture and recognition resources."""

    device: str = ""  # "" = system default output device
    threads: int = 2

    def validated(self) -> "Audio":
        cores = max(1, os.cpu_count() or 1)
        self.threads = _clamp(self.threads, 1, min(16, cores), min(2, cores))
        if not isinstance(self.device, str):
            self.device = ""
        return self


@dataclass
class Settings:
    appearance: Appearance = field(default_factory=Appearance)
    geometry: Geometry = field(default_factory=Geometry)
    behaviour: Behaviour = field(default_factory=Behaviour)
    audio: Audio = field(default_factory=Audio)
    version: int = SETTINGS_VERSION

    def validated(self) -> "Settings":
        self.appearance.validated()
        self.geometry.validated()
        self.behaviour.validated()
        self.audio.validated()
        return self

    def copy(self) -> "Settings":
        return Settings(
            appearance=Appearance(**asdict(self.appearance)),
            geometry=Geometry(**asdict(self.geometry)),
            behaviour=Behaviour(**asdict(self.behaviour)),
            audio=Audio(**asdict(self.audio)),
            version=self.version,
        )


def _build(cls, data: dict | None):
    allowed = {f.name for f in fields(cls)}
    clean = {key: value for key, value in (data or {}).items() if key in allowed}
    return cls(**clean)


def _build_settings(data: dict) -> Settings:
    raw_version = data.get("version", SETTINGS_VERSION)
    try:
        version = int(raw_version)
    except (TypeError, ValueError):
        version = SETTINGS_VERSION
    return Settings(
        appearance=_build(Appearance, data.get("appearance")),
        geometry=_build(Geometry, data.get("geometry")),
        behaviour=_build(Behaviour, data.get("behaviour")),
        audio=_build(Audio, data.get("audio")),
        version=version,
    ).validated()


def _quarantine(path: Path) -> None:
    """Keep a broken settings.json next to the new one instead of silently dropping it."""
    try:
        broken = path.with_suffix(path.suffix + ".broken")
        path.replace(broken)
        log.warning("settings_quarantined path=%s moved_to=%s", path, broken)
    except Exception as exc:  # noqa: BLE001
        log.warning("settings_quarantine_failed path=%s error=%r", path, exc)


def load_settings() -> Settings:
    path = settings_path()
    if not path.exists():
        log.info("settings_load path=%s result=defaults", path)
        return Settings().validated()
    try:
        # utf-8-sig: Notepad and some editors save settings.json with a BOM, and a
        # plain utf-8 read then fails on the first byte.
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:  # noqa: BLE001
        log.warning("settings_load_failed path=%s error=%r result=defaults", path, exc)
        _quarantine(path)
        return Settings().validated()
    if not isinstance(data, dict):
        log.warning("settings_load_failed path=%s error=not_a_mapping result=defaults", path)
        _quarantine(path)
        return Settings().validated()
    try:
        settings = _build_settings(data)
    except Exception as exc:  # noqa: BLE001
        log.warning("settings_load_failed path=%s error=%r result=defaults", path, exc)
        _quarantine(path)
        return Settings().validated()
    version = settings.version
    appearance = settings.appearance
    if version < 5:
        raw_appearance = data.get("appearance")
        old = raw_appearance if isinstance(raw_appearance, dict) else {}

        def to_transparency(alpha_value, fallback: int) -> int:
            if alpha_value is None:
                return fallback
            try:
                return max(0, min(100, round(100 - int(alpha_value) / 255 * 100)))
            except (TypeError, ValueError):
                log.warning("settings_value_invalid field=opacity value=%r fallback=%d", alpha_value, fallback)
                return fallback

        appearance.text_transparency = to_transparency(old.get("history_opacity"), 80)
        appearance.tail_transparency = 0
        appearance.history_transparency = to_transparency(old.get("history_opacity"), 80)
        appearance.outline_transparency = to_transparency(old.get("outline_opacity"), 0)
        appearance.backdrop_transparency = to_transparency(old.get("backdrop_opacity"), 55)
        log.info(
            "settings_migrated version=%d→5 transparencies text=%d tail=%d history=%d",
            version,
            appearance.text_transparency,
            appearance.tail_transparency,
            appearance.history_transparency,
        )
    log.info("settings_load path=%s result=ok", path)
    # The installer can add the Run key on its own, so the checkbox must show what
    # Windows will really do, not what settings.json remembers.
    actual_autostart = autostart_enabled()
    if actual_autostart is not None and actual_autostart != settings.behaviour.autostart:
        log.info(
            "autostart_synced settings=%s registry=%s",
            settings.behaviour.autostart,
            actual_autostart,
        )
        settings.behaviour.autostart = actual_autostart
    if version < 8:
        was_active = appearance.text_transparency
        was_tail = appearance.tail_transparency
        appearance.text_transparency = min(was_active, was_tail)
        appearance.tail_transparency = max(was_active, was_tail)
        appearance.align = "left"
        log.info(
            "settings_migrated version=%d→8 active=%d unconfirmed=%d align=left",
            version,
            appearance.text_transparency,
            appearance.tail_transparency,
        )
    return settings


def _write_payload(path: Path, payload: str) -> None:
    """Write a sibling temp file, fsync it and rename over the target."""
    tmp_path = None
    try:
        handle, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix="settings.", suffix=".tmp")
        tmp_path = Path(tmp_name)
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp_path, path)
        tmp_path = None
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass


def save_settings(settings: Settings) -> Path:
    path = settings_path()
    settings.version = SETTINGS_VERSION
    payload = json.dumps(asdict(settings), ensure_ascii=False, indent=2)
    try:
        # A crash mid-write must never leave a half-written settings.json behind (the
        # loader would quarantine it).
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_payload(path, payload)
        log.info("settings_saved path=%s section=all", path)
    except Exception as exc:  # noqa: BLE001
        log.error("settings_save_failed path=%s error=%r", path, exc)
    return path


def save_geometry(settings: Settings) -> Path:
    """Persist only the geometry section, keeping every other key from disk.

    Dragging the plate is not a settings commit: writing the whole live object dumped
    the dialog preview values into settings.json, so Cancel changed nothing.
    """
    path = settings_path()
    try:
        current = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
    except Exception as exc:  # noqa: BLE001
        log.warning("settings_geometry_load_failed path=%s error=%r", path, exc)
        current = {}
    if not isinstance(current, dict):
        current = {}
    current["version"] = SETTINGS_VERSION
    current["geometry"] = asdict(settings.geometry)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_payload(path, json.dumps(current, ensure_ascii=False, indent=2))
        log.info("settings_saved path=%s section=geometry", path)
    except Exception as exc:  # noqa: BLE001
        log.error("settings_geometry_save_failed path=%s error=%r", path, exc)
    return path
