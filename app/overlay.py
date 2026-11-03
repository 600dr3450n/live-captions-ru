"""Subtitle overlay window: transparent, click-through, always on top."""
from __future__ import annotations

import ctypes
import logging

from dataclasses import asdict

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

from settings import Geometry, Settings
from text_layout import (
    MAX_ACTIVE_WORDS,
    alpha_from_transparency,
    build_font,
    draw_word,
    qcolor,
    split_long_word,
    wrap_flagged,
)

log = logging.getLogger(__name__)

WDA_EXCLUDEFROMCAPTURE = 0x00000011
HWND_TOPMOST = 0xFFFFFFFFFFFFFFFF
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002

_USER32 = None


def _user32():
    """Cached user32 with explicit prototypes.

    Without argtypes ctypes guesses the pointer width; on 64-bit Windows a guessed
    HWND argument is the classic source of silent SetWindowPos failures.
    """
    global _USER32
    if _USER32 is None:
        # use_last_error is required for ctypes.get_last_error(): plain windll leaves
        # it untouched, so every logged api_error was 0 instead of the real code.
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.SetWindowPos.argtypes = (
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint,
        )
        user32.SetWindowPos.restype = ctypes.c_bool
        user32.SetWindowDisplayAffinity.argtypes = (ctypes.c_void_p, ctypes.c_uint)
        user32.SetWindowDisplayAffinity.restype = ctypes.c_bool
        _USER32 = user32
    return _USER32
SWP_NOACTIVATE = 0x0010
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000

HANDLE_SIZE = 12
HANDLE_GRAB = 8
MIN_BOX_WIDTH = 200  # the two edit-mode buttons have to fit side by side
MIN_TEXT_WIDTH = 40  # never squeeze the text column below this
BUTTON_SIZE = (92, 28)
DONE_BUTTON = BUTTON_SIZE
CANCEL_BUTTON = BUTTON_SIZE
# Topmost reassert cadence: 5 s is enough inside the work area, but a box parked on
# the taskbar has to win the z-order fight after every taskbar click.
TOPMOST_INTERVAL_MS = 5000
TOPMOST_FAST_INTERVAL_MS = 700
SNAP_DISTANCE = 16

PREVIEW_HISTORY = "живые субтитры на русском языке в режиме"
PREVIEW_COMMITTED = "реального времени без доступа к"
PREVIEW_TAIL = "сети"
PREVIEW_TEXT = " ".join(["живые субтитры на русском языке"] * 6)

class SubtitleOverlay(QWidget):
    """Caption window. Does not steal focus and does not intercept mouse input (unless editing)."""

    def __init__(self, settings: Settings, exclude_from_capture: bool = True) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._settings = settings
        self._exclude_from_capture = exclude_from_capture
        self._text = ""
        self._confirmed = 0
        self._colors = (0, 0)
        self._colors_target = (0, 0)
        self._captions_on = settings.behaviour.start_visible
        self._edit_mode = False
        self._preview = False
        self._drag_mode: str | None = None
        self._drag_origin: QPoint | None = None
        self._drag_start_rect = None
        self._edit_start_rect: QRect | None = None
        self._edit_start_geometry = None
        self._resize_origin: QPoint | None = None
        self._lines: list[tuple[list[tuple[float, str, QColor]], int]] = []
        self._line_height = 1
        self._on_geometry_changed = None
        self._on_edit_finished = None

        self._font = build_font(settings.appearance)
        self._metrics = QFontMetrics(self._font)

        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self._clear_idle)
        self._on_idle_clear = None

        self._topmost_timer = QTimer(self)
        self._topmost_timer.timeout.connect(self._reassert_topmost)
        self._topmost_timer.start(TOPMOST_INTERVAL_MS)

        self.setWindowTitle("Live Captions RU")
        self.setMouseTracking(True)
        self._ready = False
        if self._exclude_from_capture:
            self._apply_capture_exclusion()
        self.apply_settings(settings)

    # ------------------------------------------------------------------ API
    def set_ready(self, ready: bool = True) -> None:
        """Show the window only after the model is loaded.

        Visibility follows the captions state: when captions are switched off at
        startup the box must not appear at all, backdrop included. The settings
        dialog still shows it as a preview through set_preview().
        """
        self._ready = bool(ready)
        if self._ready:
            width, height = self._box_size()
            x, y = self._box_position(width, height)
            self.setGeometry(x, y, width, height)
            if self._captions_on or self._preview:
                self.show()
                self._apply_capture_exclusion()
            else:
                log.debug("box_ready_hidden reason=captions_off")
            self._relayout()
            self.update()

    def set_geometry_callback(self, callback) -> None:
        """main() passes a callable invoked after the box is moved/resized in edit mode."""
        self._on_geometry_changed = callback

    def set_edit_finished_callback(self, callback) -> None:
        self._on_edit_finished = callback

    def set_idle_callback(self, callback) -> None:
        self._on_idle_clear = callback

    def apply_settings(self, settings: Settings) -> None:
        self._settings = settings
        self._font = build_font(settings.appearance)
        self._metrics = QFontMetrics(self._font)
        self._captions_on = settings.behaviour.start_visible if self._captions_on is None else self._captions_on
        if settings.behaviour.idle_clear_sec > 0:
            self._idle_timer.setInterval(settings.behaviour.idle_clear_sec * 1000)
        else:
            self._idle_timer.stop()
        self._relayout()
        if not self._captions_on and not self._preview:
            self.hide()
        elif not self.isVisible() and self._ready:
            self.show()

    def set_text(
        self,
        text: str,
        confirmed: int = 0,
        highlight_start: int = 0,
        highlight_end: int = 0,
    ) -> None:
        if not self._captions_on or self._preview:
            return
        state = (text, confirmed, highlight_start, highlight_end)
        if state == (self._text, self._confirmed, self._colors_target[0], self._colors_target[1]):
            return

        self._text = text
        self._confirmed = max(0, confirmed)
        self._colors_target = (highlight_start, highlight_end)
        self._colors = self._colors_target
        if not self.isVisible():
            self.show()
            self._apply_capture_exclusion()
        if self._settings.behaviour.idle_clear_sec > 0:
            self._idle_timer.start()
        self._relayout()

    def set_captions_visible(self, visible: bool, keep_visible: bool = False) -> None:
        self._captions_on = bool(visible)
        if self._captions_on and not self._ready and not self._preview:
            return
        if not self._captions_on:
            self._idle_timer.stop()
            if self._preview:
                self._show_preview_text()
            else:
                self._text, self._confirmed = "", 0
                self._colors = self._colors_target = (0, 0)
                self._relayout()
        if self._captions_on or (keep_visible and self._preview):
            self.show()
            self._apply_capture_exclusion()
            self._relayout()
        else:
            self.hide()
        log.debug("captions_visible value=%s", self._captions_on)

    def captions_visible(self) -> bool:
        return self._captions_on

    def _show_preview_text(self) -> None:
        """Show the tail of a repeated phrase; only the last copy carries the markup."""
        self._text = PREVIEW_TEXT
        words = PREVIEW_TEXT.split()
        # previous: the first five copies, active: four words of the last one, tail: "языке"
        begin = len(words) - 5
        finish = len(words) - 1
        self._confirmed = finish
        self._colors = (begin, finish)
        self._colors_target = self._colors
        self._idle_timer.stop()
        self._relayout()

    def set_preview(self, enabled: bool) -> None:
        self._preview = bool(enabled)
        if self._preview:
            self._show_preview_text()
            self.show()
            self._apply_capture_exclusion()
            log.debug("preview_mode value=on")
        else:
            self._text = ""
            self._confirmed = 0
            self._colors = self._colors_target = (0, 0)
            # Captions can be switched off from the tray menu while the dialog is
            # open: the preview kept the box on screen, and closing the dialog only
            # cleared the text, leaving an empty backdrop behind.
            if not self._captions_on:
                self.hide()
            log.debug("preview_mode value=off")
        self._relayout()

    def preview_mode(self) -> bool:
        return self._preview

    def begin_edit_mode(self) -> None:
        if self._edit_mode:
            return
        self._edit_mode = True
        self._edit_start_rect = QRect(self.geometry())
        self._edit_start_geometry = Geometry(**asdict(self._settings.geometry))
        self.show()
        self._set_click_through(False)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self._relayout()
        log.debug("edit_mode value=on")

    def end_edit_mode(self, save: bool = True) -> None:
        if not self._edit_mode:
            return
        if save:
            self._commit_geometry()
        elif self._edit_start_geometry is not None:
            self._settings.geometry = self._edit_start_geometry
            if self._edit_start_rect is not None:
                self.setGeometry(self._edit_start_rect)
            self._relayout()
        self._edit_mode = False
        self._set_click_through(True)
        self.unsetCursor()
        self._apply_capture_exclusion()
        self._relayout()
        if self._on_edit_finished is not None:
            self._on_edit_finished()
        log.debug(
            "edit_mode value=off saved=%s box_x=%d box_y=%d box_w=%d box_h=%d",
            save,
            self.x(),
            self.y(),
            self.width(),
            self.height(),
        )
        if self._on_geometry_changed is not None:
            self._on_geometry_changed()

    def edit_mode(self) -> bool:
        return self._edit_mode

    def _set_click_through(self, enabled: bool) -> None:
        flags = self.windowFlags()
        if enabled:
            flags |= Qt.WindowType.WindowTransparentForInput
        else:
            flags &= ~Qt.WindowType.WindowTransparentForInput
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, enabled)
        if flags != self.windowFlags():
            visible = self.isVisible()
            self.setWindowFlags(flags)
            if visible:
                self.show()
            self._apply_capture_exclusion()
            self._reassert_topmost()
        log.info("click_through value=%s", enabled)

    def _screen(self):
        screens = QGuiApplication.screens()
        if not screens:
            # No screens at all (detached session, remote desktop before login):
            # primaryScreen() is None there, so callers must get something usable.
            return QGuiApplication.primaryScreen()
        index = min(max(self._settings.geometry.monitor, 0), len(screens) - 1)
        return screens[index]

    def _screen_rect(self) -> QRect:
        screen = self._screen()
        if screen is None:
            log.warning("no_screen_found action=use_virtual_rect")
            return QRect(0, 0, 1920, 1080)
        if self._settings.geometry.avoid_taskbar:
            return screen.availableGeometry()
        return screen.geometry()

    def _screen_bounds(self) -> QRect:
        """Full screen rectangle, taskbar included.

        A custom position is allowed to sit on the taskbar: the ready-made minimal
        style parks the box next to the Start button. Clamping and snapping must
        therefore use the whole screen, not the work area.
        """
        screen = self._screen()
        if screen is None:
            log.warning("no_screen_found action=use_virtual_rect")
            return QRect(0, 0, 1920, 1080)
        return screen.geometry()

    def _box_size(self) -> tuple[int, int]:
        rect = self._screen_rect()
        geometry = self._settings.geometry
        appearance = self._settings.appearance
        width = geometry.width_px if geometry.width_px > 0 else int(rect.width() * geometry.width_percent / 100)
        # Horizontal padding is drawn as a raw offset, so it has to fit inside the box
        # together with a usable text column; 200 px is also the width the two edit
        # buttons need. Height is clamped to the screen: only the position used to be.
        minimum = max(MIN_BOX_WIDTH, 2 * appearance.padding_x + MIN_TEXT_WIDTH)
        width = max(minimum, min(width, rect.width() - 20))
        height = int(appearance.padding_y * 2 + geometry.max_lines * self._line_height)
        height = max(1, min(height, rect.height() - 20))
        return width, height

    def _box_position(self, width: int, height: int) -> tuple[int, int]:
        rect = self._screen_rect()
        bounds = self._screen_bounds()
        geometry = self._settings.geometry
        if geometry.position == "custom" and geometry.x >= 0 and geometry.y >= 0:
            # x/y are offsets inside the screen when they fit it, absolute otherwise;
            # either way clamp the result so a saved geometry from another monitor or a
            # different DPI cannot park the box off screen. The clamp uses the full
            # screen: a box parked on the taskbar is intentional, not an error.
            x = rect.x() + geometry.x if geometry.x < rect.width() else geometry.x
            y = rect.y() + geometry.y if geometry.y < rect.height() else geometry.y
            x = max(bounds.x(), min(int(x), bounds.x() + max(0, bounds.width() - width)))
            y = max(bounds.y(), min(int(y), bounds.y() + max(0, bounds.height() - height)))
            return int(x), int(y)
        x = rect.x() + (rect.width() - width) // 2
        if geometry.position == "top":
            y = rect.y() + geometry.margin
        elif geometry.position == "center":
            y = rect.y() + (rect.height() - height) // 2
        else:  # bottom
            y = rect.bottom() - height - geometry.margin
        return int(x), int(y)

    def _relayout(self) -> None:
        appearance = self._settings.appearance
        metrics = self._metrics
        space = metrics.horizontalAdvance(" ")
        self._line_height = max(1, int(metrics.height() * appearance.line_spacing))

        width, height = self._box_size()
        text_width = max(MIN_TEXT_WIDTH, width - 2 * appearance.padding_x)

        active_color = qcolor(appearance.text_color, alpha_from_transparency(appearance.text_transparency))
        unconfirmed_color = qcolor(appearance.text_color, alpha_from_transparency(appearance.tail_transparency))
        past_color = qcolor(appearance.text_color, alpha_from_transparency(appearance.history_transparency))

        words = self._text.split()
        if appearance.uppercase:
            words = [w.upper() for w in words]
        dropped = max(0, len(words) - MAX_ACTIVE_WORDS)
        words = words[dropped:]
        confirmed = max(0, min(self._confirmed - dropped, len(words)))
        start = max(0, min(self._colors[0] - dropped, confirmed))
        end = max(start, min(self._colors[1] - dropped, confirmed))
        confirmed_words = words[:confirmed]
        pending_words = words[confirmed:]

        active_lines: list[tuple[list[tuple[float, str, QColor]], int]] = []
        for line_words, line_width in wrap_flagged(
            [(word, start <= index < end) for index, word in enumerate(confirmed_words)],
            metrics,
            space,
            text_width,
        ):
            rendered = [(x, word, active_color if flag else past_color) for x, word, flag in line_words]
            active_lines.append((rendered, line_width))

        if pending_words:
            if not active_lines:
                active_lines.append(([], 0))
            for word in pending_words:
                for index, piece in enumerate(split_long_word(word, metrics, text_width)):
                    line_words, line_width = active_lines[-1]
                    end_x = max(
                        (word_x + metrics.horizontalAdvance(existing) for word_x, existing, _color in line_words),
                        default=0.0,
                    )
                    word_width = metrics.horizontalAdvance(piece)
                    gap = float(space) if line_words and index == 0 else 0.0
                    if line_words and end_x + gap + word_width > text_width:
                        active_lines.append(([], 0))
                        line_words, line_width = active_lines[-1]
                        end_x = 0.0
                        gap = 0.0
                    position = end_x + gap
                    line_width = max(line_width, int(position + word_width))
                    active_lines[-1] = (line_words + [(position, piece, unconfirmed_color)], line_width)

        max_lines = self._settings.geometry.max_lines
        visible_active = active_lines[-max_lines:] if active_lines else []

        # Dimming is decided per word by the highlight window, not per line, so the
        # colouring built above is used as is and no line is demoted for being old.
        self._lines = [
            (line_words, line_width, self._line_x0(line_width, width, appearance))
            for line_words, line_width in visible_active
        ]

        x, y = self._box_position(width, height)
        if self.x() != x or self.y() != y or self.width() != width or self.height() != height:
            self.setGeometry(x, y, width, height)
        self.update()

    def _line_x0(self, line_width: int, box_width: int, appearance) -> float:
        if appearance.align == "right":
            return float(box_width - appearance.padding_x - line_width)
        if appearance.align == "left":
            return float(appearance.padding_x)
        return (box_width - line_width) / 2.0

    def _clear_idle(self) -> None:
        self._text, self._confirmed = "", 0
        self._colors = self._colors_target = (0, 0)
        self._relayout()
        if self._on_idle_clear is not None:
            self._on_idle_clear()
    def _topmost_interval_ms(self) -> int:
        """Reassert faster while the box sits on the taskbar.

        Clicking the taskbar raises it above every topmost window, so a box parked
        on the taskbar (the minimal style) would disappear under it until the next
        reassert. Outside the taskbar band the slow interval is enough.
        """
        screen = self._screen()
        if screen is None:
            return TOPMOST_INTERVAL_MS
        try:
            if screen.availableGeometry().contains(self.geometry()):
                return TOPMOST_INTERVAL_MS
        except Exception:  # noqa: BLE001
            return TOPMOST_INTERVAL_MS
        return TOPMOST_FAST_INTERVAL_MS

    def _reassert_topmost(self) -> None:
        if not self.isVisible():
            return
        interval = self._topmost_interval_ms()
        if interval != self._topmost_timer.interval():
            self._topmost_timer.setInterval(interval)
        try:
            ok = _user32().SetWindowPos(
                ctypes.c_void_p(int(self.winId())),
                ctypes.c_void_p(HWND_TOPMOST),
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
            )
            if not ok:
                log.debug("topmost_reassert_failed api_error=%s", ctypes.get_last_error())
        except Exception as exc:  # noqa: BLE001
            log.debug("topmost_reassert_failed error=%r", exc)

    def _apply_capture_exclusion(self) -> None:
        """Captions must not appear in screen sharing or screenshots."""
        try:
            user32 = _user32()
            affinity = WDA_EXCLUDEFROMCAPTURE if self._exclude_from_capture else 0
            applied = user32.SetWindowDisplayAffinity(ctypes.c_void_p(int(self.winId())), affinity)
            if not applied:
                log.warning(
                    "capture_exclusion_failed api_error=%s value=%s",
                    ctypes.get_last_error(),
                    self._exclude_from_capture,
                )
            else:
                log.info("capture_exclusion value=%s", "enabled" if self._exclude_from_capture else "disabled")
        except Exception as exc:  # noqa: BLE001
            log.warning("capture_exclusion_failed error=%r", exc)

    def _done_rect(self) -> QRect:
        """OK sits on the left, the Windows convention."""
        # Clamped: with a box narrower than the two buttons OK was drawn outside the
        # window and could not be clicked, which left Cancel as the only way out.
        x = max(2, self.width() - DONE_BUTTON[0] - CANCEL_BUTTON[0] - 16)
        return QRect(x, 6, DONE_BUTTON[0], DONE_BUTTON[1])

    def _cancel_rect(self) -> QRect:
        x = max(2, self.width() - CANCEL_BUTTON[0] - 8)
        return QRect(x, 6, CANCEL_BUTTON[0], CANCEL_BUTTON[1])

    def _handle_rects(self) -> dict[str, QRect]:
        width, height = self.width(), self.height()
        half = HANDLE_SIZE // 2
        points = {
            "nw": (0, 0),
            "n": (width // 2, 0),
            "ne": (width, 0),
            "e": (width, height // 2),
            "se": (width, height),
            "s": (width // 2, height),
            "sw": (0, height),
            "w": (0, height // 2),
        }
        return {name: QRect(x - half, y - half, HANDLE_SIZE, HANDLE_SIZE) for name, (x, y) in points.items()}

    def _handle_at(self, position: QPoint) -> str | None:
        for name, rect in self._handle_rects().items():
            if rect.adjusted(-HANDLE_GRAB, -HANDLE_GRAB, HANDLE_GRAB, HANDLE_GRAB).contains(position):
                return name
        return None

    @staticmethod
    def _cursor_for(handle: str | None) -> Qt.CursorShape:
        return {
            "nw": Qt.CursorShape.SizeFDiagCursor,
            "se": Qt.CursorShape.SizeFDiagCursor,
            "ne": Qt.CursorShape.SizeBDiagCursor,
            "sw": Qt.CursorShape.SizeBDiagCursor,
            "n": Qt.CursorShape.SizeVerCursor,
            "s": Qt.CursorShape.SizeVerCursor,
            "e": Qt.CursorShape.SizeHorCursor,
            "w": Qt.CursorShape.SizeHorCursor,
        }.get(handle or "", Qt.CursorShape.SizeAllCursor)

    def _snap_rect(self, rect: QRect, mode: str) -> QRect:
        screen = self._screen_bounds()
        result = QRect(rect)
        if mode == "move" or "w" in mode:
            if abs(result.left() - screen.left()) <= SNAP_DISTANCE:
                result.setLeft(screen.left())
        if mode == "move" or "e" in mode:
            if abs(result.right() - screen.right()) <= SNAP_DISTANCE:
                result.setRight(screen.right())
        if mode == "move" or "n" in mode:
            if abs(result.top() - screen.top()) <= SNAP_DISTANCE:
                result.setTop(screen.top())
        if mode == "move" or "s" in mode:
            if abs(result.bottom() - screen.bottom()) <= SNAP_DISTANCE:
                result.setBottom(screen.bottom())
        return result

    def _drag_screen_bounds(self, rect: QRect) -> QRect:
        """Bounds of the screen the box is being dragged on."""
        screen = QGuiApplication.screenAt(rect.center())
        if screen is None:
            return self._screen_bounds()
        return screen.geometry()

    def _clamp_to_screen(self, rect: QRect) -> QRect:
        bounds = self._drag_screen_bounds(rect)
        result = QRect(rect)
        if result.width() <= bounds.width():
            result.moveLeft(max(bounds.left(), min(result.left(), bounds.right() - result.width() + 1)))
        if result.height() <= bounds.height():
            result.moveTop(max(bounds.top(), min(result.top(), bounds.bottom() - result.height() + 1)))
        return result

    def _commit_geometry(self) -> None:
        geometry = self._settings.geometry
        start = self._edit_start_rect
        if start is None or (start.x() == self.x() and start.y() == self.y()
                             and start.width() == self.width() and start.height() == self.height()):
            self._relayout()
            return
        # Store the offsets against the monitor the plate actually sits on, and remember
        # that monitor: otherwise a plate dragged to a second screen jumped back to the
        # edge of the configured one on the next relayout.
        screen = QGuiApplication.screenAt(self.geometry().center())
        bounds = screen.geometry() if screen is not None else self._screen_bounds()
        if screen is not None:
            screens = QGuiApplication.screens()
            try:
                geometry.monitor = screens.index(screen)
            except ValueError:
                pass
        geometry.position = "custom"
        geometry.x = max(0, self.x() - bounds.x())
        geometry.y = max(0, self.y() - bounds.y())
        geometry.width_px = max(200, self.width())
        lines = round((self.height() - 2 * self._settings.appearance.padding_y) / max(1, self._line_height))
        geometry.max_lines = max(1, min(8, lines))
        self._relayout()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if not self._edit_mode:
            return
        position = event.position().toPoint()
        if self._done_rect().contains(position):
            self.end_edit_mode(save=True)
            event.accept()
            return
        if self._cancel_rect().contains(position):
            self.end_edit_mode(save=False)
            event.accept()
            return
        handle = self._handle_at(position)
        if handle:
            self._drag_mode = handle
        elif self.rect().contains(position):
            self._drag_mode = "move"
        else:
            self._drag_mode = None
        if self._drag_mode:
            self._drag_origin = event.globalPosition().toPoint()
            self._drag_start_rect = QRect(self.geometry())
            self.setCursor(self._cursor_for(handle))
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if not self._edit_mode:
            return
        position = event.position().toPoint()
        if self._drag_mode is None or self._drag_origin is None or self._drag_start_rect is None:
            if self._done_rect().contains(position) or self._cancel_rect().contains(position):
                self.setCursor(Qt.CursorShape.ArrowCursor)
            else:
                handle = self._handle_at(position)
                if handle:
                    self.setCursor(self._cursor_for(handle))
                elif self.rect().contains(position):
                    self.setCursor(Qt.CursorShape.SizeAllCursor)
                else:
                    self.unsetCursor()
            return

        delta = event.globalPosition().toPoint() - self._drag_origin
        start = self._drag_start_rect
        mode = self._drag_mode
        rect = QRect(start)
        if mode == "move":
            rect.moveTopLeft(start.topLeft() + delta)
        else:
            if "n" in mode:
                rect.setTop(start.top() + delta.y())
            if "s" in mode:
                rect.setBottom(start.bottom() + delta.y())
            if "w" in mode:
                rect.setLeft(start.left() + delta.x())
            if "e" in mode:
                rect.setRight(start.right() + delta.x())

        min_width = 200
        min_height = int(self._line_height + 2 * self._settings.appearance.padding_y)
        if rect.width() < min_width:
            if "w" in mode or mode == "move":
                rect.setLeft(rect.right() - min_width)
            else:
                rect.setRight(rect.left() + min_width)
        if rect.height() < min_height:
            if "n" in mode or mode == "move":
                rect.setTop(rect.bottom() - min_height)
            else:
                rect.setBottom(rect.top() + min_height)

        # Clamp to the screen under the box, not to the one saved in the settings:
        # dragging the plate to a second monitor has to be possible.
        rect = self._clamp_to_screen(rect)
        configured = self._screen()
        if configured is not None and configured.geometry().contains(rect.center()):
            rect = self._snap_rect(rect, mode)
            rect = self._clamp_to_screen(rect)
        self.setGeometry(rect)
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if not self._edit_mode:
            return
        if self._drag_mode:
            self._drag_mode = None
            self._drag_origin = None
            self._drag_start_rect = None
            self._commit_geometry()
            self.setCursor(self._cursor_for(self._handle_at(event.position().toPoint())))
        event.accept()

    def paintEvent(self, event) -> None:  # noqa: N802
        appearance = self._settings.appearance
        box = QRect(0, 0, self.width(), self.height())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setFont(self._font)

        if appearance.backdrop_enabled:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(
                qcolor(appearance.backdrop_color, alpha_from_transparency(appearance.backdrop_transparency))
            )
            painter.drawRoundedRect(
                QRectF(box).adjusted(0.5, 0.5, -0.5, -0.5), appearance.corner_radius, appearance.corner_radius
            )

        if self._lines:
            painter.save()
            painter.setClipRect(box)
            outline_color = qcolor(
                appearance.outline_color, alpha_from_transparency(appearance.outline_transparency)
            )
            outline_width = max(0.0, appearance.outline_width) if appearance.outline_enabled else 0.0
            total_height = len(self._lines) * self._line_height
            baseline = box.bottom() - appearance.padding_y - total_height + self._metrics.ascent()
            for index, (words, line_width, base_x0) in enumerate(self._lines):
                x0 = box.left() + base_x0
                for x, word, color in words:
                    word_alpha = color.alpha()
                    word_outline = QColor(outline_color)
                    word_outline.setAlpha(round(outline_color.alpha() * word_alpha / 255))
                    draw_word(
                        painter,
                        x0 + x,
                        baseline,
                        word,
                        color,
                        word_outline,
                        outline_width if word_alpha > 0 else 0.0,
                        appearance.shadow_size if appearance.shadow and word_alpha > 0 else 0,
                        QColor(0, 0, 0, int(150 * word_alpha / 255)),
                    )
                baseline += self._line_height
            painter.restore()

        if self._edit_mode:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(90, 170, 255, 34))
            painter.drawRect(box)
            pen = QPen(QColor(90, 170, 255, 230))
            pen.setWidthF(2.0)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(pen)
            painter.drawRect(box.adjusted(1, 1, -2, -2))
            painter.setPen(QPen(QColor(255, 255, 255, 235), 1))
            painter.setBrush(QColor(90, 170, 255, 245))
            for handle_rect in self._handle_rects().values():
                painter.drawRect(handle_rect.adjusted(0, 0, -1, -1))
            font = QFont(self._settings.appearance.font_family)
            font.setPixelSize(13)
            font.setWeight(QFont.Weight.Normal)
            painter.setFont(font)
            for rect, caption, strong in (
                (self._done_rect(), "ОК", True),
                (self._cancel_rect(), "Отмена", False),
            ):
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(90, 170, 255, 225) if strong else QColor(70, 74, 84, 220))
                painter.drawRoundedRect(rect, 6, 6)
                painter.setPen(QColor(255, 255, 255))
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, caption)
        painter.end()
