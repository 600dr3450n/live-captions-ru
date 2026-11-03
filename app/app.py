"""Application object: tray, pipeline lifecycle, settings wiring."""
from __future__ import annotations

import ctypes
import logging
import os
import queue
import subprocess
import sys
import threading
import time

from PySide6.QtCore import QEasingCurve, QObject, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

import paths
from asr import TOneStreamingASR
from capture import LoopbackCapture
from config import (
    CREATE_NEW_PROCESS_GROUP,
    DETACHED_PROCESS,
    ENV_CAPTURE_EXCLUSION,
    ENV_RECYCLE_COUNT,
    LOAD_RETRY_MAX_MS,
    LOAD_RETRY_MIN_MS,
    RELAUNCH_WAIT_ARG,
    RESTART_FORGIVE_SECONDS,
    RESTART_MAX_INTERVAL,
    RESTART_MIN_INTERVAL,
    RSS_LIMIT_MB,
    RSS_RECYCLE_MAX,
    SILENCE_SECONDS,
    STALL_SECONDS,
    TAKEOVER_ARG,
    WATCHDOG_SECONDS,
)
from icons import make_icon
from overlay import SubtitleOverlay
from settings import Settings, save_geometry, save_settings
from settings_dialog import SettingsDialog
from worker import RecognitionWorker

log = logging.getLogger("main")


def _recycle_count() -> int:
    """How many times this process was relaunched by the memory watchdog.

    The counter has to survive the relaunch, so it travels in the environment of the
    new process instead of living in a field.
    """
    try:
        return max(0, int(os.environ.get(ENV_RECYCLE_COUNT, "0")))
    except ValueError:
        return 0


def _num(value, default: float) -> float:
    """Read a stats field that legitimately can be 0.0 or -1.0.

    `float(x or default)` turned "just now" (0.0) into "never" (-1.0), so the watchdog
    saw no sound while audio was continuous and treated a fresh emit as a stale one.
    """
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class CaptionsApp(QObject):
    text_ready = Signal(str, int, int, int)
    pipeline_ready = Signal()
    pipeline_failed = Signal(str)
    pipeline_restarted = Signal()
    relaunch_requested = Signal(str)

    def __init__(self, app: QApplication, settings: Settings) -> None:
        super().__init__()
        self._app = app
        self._settings = settings
        self._snapshot = settings.copy()

        excluded = os.environ.get(ENV_CAPTURE_EXCLUSION, "1").strip() not in ("0", "false", "no")
        self.overlay = SubtitleOverlay(settings, exclude_from_capture=excluded)
        self.overlay.set_idle_callback(self._on_idle_clear)
        self.overlay.set_geometry_callback(self._on_geometry_edited)
        self.overlay.set_edit_finished_callback(self._after_edit_mode)
        # Explicit queued connection: the worker thread must never touch the overlay directly.
        self.text_ready.connect(self.overlay.set_text, Qt.QueuedConnection)
        log.debug("capture_exclusion_setting value=%s", excluded)

        self._dialog: SettingsDialog | None = None
        self._reopen_settings_after_edit = False
        self._stopping = False
        self._restart_after_load = False
        self._load_failed = False
        self._load_attempts = 0
        self._load_inflight = False
        self._restart_thread: threading.Thread | None = None
        self._loading = False
        self._pending_settings = None
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._flush_preview)
        self._pulse = QVariantAnimation(self)
        self._pulse.setStartValue(1.0)
        self._pulse.setKeyValueAt(0.5, 0.6)
        self._pulse.setEndValue(1.0)
        self._pulse.setDuration(1000)
        self._pulse.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._pulse.setLoopCount(-1)
        self._pulse.valueChanged.connect(self._pulse_tick)
        self.pipeline_ready.connect(self._on_pipeline_ready)
        self.pipeline_failed.connect(self._on_pipeline_failed)
        self.pipeline_restarted.connect(self._on_pipeline_restarted, Qt.QueuedConnection)
        self.relaunch_requested.connect(self._on_relaunch_requested, Qt.QueuedConnection)
        self._audio_queue: "queue.Queue" = queue.Queue(maxsize=80)
        self._capture: LoopbackCapture | None = None
        self._worker: RecognitionWorker | None = None
        self._asr: TOneStreamingASR | None = None
        self._pipeline_lock = threading.Lock()

        # (icon_on, kind, text) of the icon currently in the tray: the shell rebuilds
        # the icon on every setIcon call, and the status timer fires every two seconds.
        # The tooltip is set once below and never changes: hovering the tray icon always
        # shows the program name, the state lives in the icon itself.
        self._icon_state: tuple[bool, str, str] | None = None
        self._recycle_warned = False
        # Tick counter for the once-a-minute pipeline log; must exist before the first
        # _update_status() call below, not only before the timer starts.
        self._stats_tick = 0
        self.tray = QSystemTrayIcon(make_icon(settings.behaviour.start_visible, ""))
        self.tray.setToolTip(paths.APP_DISPLAY_NAME)
        self._build_menu()
        self.tray.show()
        self._update_status()

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._update_status)
        self._status_timer.start(2000)

        self._last_restart_at = 0.0
        self._last_reconnect_at = 0.0
        self._last_worker_errors = 0
        self._last_capture_dropped = 0
        self._restarts = 0
        self._stuck_restarts = 0
        self._started_at = time.monotonic()
        self._workdir = os.getcwd()
        self._watchdog_timer = QTimer(self)
        self._watchdog_timer.timeout.connect(self._watchdog_tick)
        self._watchdog_timer.start(int(WATCHDOG_SECONDS * 1000))
        self._recycle_timer = QTimer(self)
        self._recycle_timer.timeout.connect(self._maybe_recycle)
        self._recycle_timer.start(30_000)

    @staticmethod
    def _rss_mb() -> float:
        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("faults", ctypes.c_ulong),
                ("peak_ws", ctypes.c_size_t),
                ("ws", ctypes.c_size_t),
                ("quota_peak_paged", ctypes.c_size_t),
                ("quota_paged", ctypes.c_size_t),
                ("quota_peak_nonpaged", ctypes.c_size_t),
                ("quota_nonpaged", ctypes.c_size_t),
                ("pagefile", ctypes.c_size_t),
                ("pagefile_peak", ctypes.c_size_t),
            ]

        kernel32 = ctypes.windll.kernel32
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        psapi = ctypes.windll.psapi
        psapi.GetProcessMemoryInfo.argtypes = (ctypes.c_void_p, ctypes.POINTER(Counters), ctypes.c_ulong)
        psapi.GetProcessMemoryInfo.restype = ctypes.c_bool
        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        if not psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            return -1.0
        return counters.ws / 1024 / 1024

    def _maybe_recycle(self) -> None:
        rss = self._rss_mb()
        limit = float(os.environ.get("LIVECAPTIONSRU_RSS_LIMIT_MB", "0") or 0)
        threshold = limit if limit > 0 else float(RSS_LIMIT_MB)
        if rss <= threshold:
            return
        count = _recycle_count()
        if count >= RSS_RECYCLE_MAX:
            # A low threshold (or a real leak) turns the recycle into an endless loop of
            # restarts that never shows a single caption. Stop and say so instead.
            log.error(
                "self_restart_refused rss_mb=%.0f limit_mb=%.0f count=%d max=%d action=stay",
                rss,
                threshold,
                count,
                RSS_RECYCLE_MAX,
            )
            if self._recycle_warned is False:
                self._recycle_warned = True
                self._notify(
                    "Недостаточно памяти",
                    "Приложение перезапускалось из-за нехватки памяти несколько раз подряд. "
                    "Проверьте, не задан ли слишком низкий предел в LIVECAPTIONSRU_RSS_LIMIT_MB.",
                )
            return
        log.warning("self_restart rss_mb=%.0f limit_mb=%.0f action=relaunch", rss, threshold)
        self._relaunch()

    def _notify(self, title: str, message: str) -> None:
        """Show a tray balloon; silently skip when the shell has no tray."""
        log.info("notify title=%r message=%r", title, message)
        try:
            if QSystemTrayIcon.isSystemTrayAvailable():
                self.tray.showMessage(f"{paths.APP_DISPLAY_NAME}: {title}", message)
        except Exception as exc:  # noqa: BLE001
            log.debug("notify_failed error=%r", exc)

    def _relaunch(self) -> None:
        program = sys.executable
        args = [arg for arg in sys.argv[1:] if arg not in (RELAUNCH_WAIT_ARG, TAKEOVER_ARG)]
        if not getattr(sys, "frozen", False):
            args = [os.path.abspath(sys.argv[0]), *args]
        # --relaunch-wait makes the new process sleep while the old one releases
        # the single-instance mutex and the audio device.
        args.extend([RELAUNCH_WAIT_ARG, TAKEOVER_ARG])
        log.debug("relaunch program=%r args=%r workdir=%r", program, args, self._workdir)
        relaunched = False
        try:
            if self._capture is not None:
                self._capture.stop()
        except Exception as exc:  # noqa: BLE001
            log.warning("relaunch_capture_stop_failed error=%r", exc)
        try:
            if self._worker is not None:
                self._worker.stop()
                self._worker.join(timeout=2.0)
                if self._worker.is_alive():
                    log.warning("relaunch_worker_still_alive action=proceed")
        except Exception as exc:  # noqa: BLE001
            log.warning("relaunch_worker_stop_failed error=%r", exc)
        try:
            env = {key: value for key, value in os.environ.items() if not key.startswith("_PYI_")}
            env.pop("_MEIPASS", None)
            # Carry the recycle counter so the next process knows it already restarted.
            env[ENV_RECYCLE_COUNT] = str(_recycle_count() + 1)
            subprocess.Popen(
                [program, *args],
                cwd=self._workdir,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
            )
            log.debug("relaunch_started ok=true env_cleaned=true")
            relaunched = True
        except Exception as exc:  # noqa: BLE001
            log.error("relaunch_started ok=false error=%r action=stay", exc)
        if not relaunched:
            # The pipeline is already stopped at this point: exiting without a
            # replacement takes the tray icon away and stops the captions for good.
            self._recycle_warned = True
            self._notify(
                "Перезапуск не удался",
                "Не удалось запустить новую копию приложения, распознавание остановлено. "
                "Запустите приложение заново вручную.",
            )
            try:
                self._start_pipeline()
            except Exception as exc:  # noqa: BLE001
                log.error("relaunch_recovery_failed error=%r", exc)
            return
        self.shutdown()


    def _status_kind(self) -> tuple[str, str]:
        if self._capture is None or self._worker is None:
            if self._load_failed:
                # Without this the tray said "Запускаюсь…" forever after a broken model
                # file: the app looked alive while nothing was recognising.
                return "danger", "Ошибка: модель не загрузилась"
            return "muted", "Запускаюсь…"
        capture, worker = self._pipeline_stats()
        if not capture.get("alive") or not worker.get("alive"):
            return "danger", "Ошибка: распознавание остановлено"
        zero_run = _num(capture.get("zero_run_seconds"), 0.0)
        since_emit = _num(worker.get("seconds_since_emit"), -1.0)
        if zero_run > 300:
            return "warn", "Переподключаю звук…"
        if since_emit > 180 and zero_run < 5:
            return "warn", "Звук есть, текста нет"
        if worker.get("chunks", 0) == 0:
            return "warn", "Жду звук…"
        return "ok", "Слушаю"

    # ------------------------------------------------------- watchdog/heartbeat
    def _pipeline_stats(self) -> tuple[dict, dict]:
        capture = self._capture.stats() if self._capture is not None else {}
        worker = self._worker.stats() if self._worker is not None else {}
        return capture, worker

    def _watchdog_tick(self) -> None:
        if self._capture is None or self._worker is None:
            return
        capture, worker = self._pipeline_stats()
        now = time.monotonic()

        if not worker.get("alive") or not capture.get("alive"):
            log.error(
                "watchdog_thread_dead worker_alive=%s capture_alive=%s action=pipeline_restart",
                worker.get("alive"),
                capture.get("alive"),
            )
            self._safe_restart("thread_dead")
            return

        # 0.0 means "right now" for both distances and must not be read as "never".
        zero_run = _num(capture.get("zero_run_seconds"), 0.0)
        since_emit = _num(worker.get("seconds_since_emit"), -1.0)
        since_loud = _num(capture.get("seconds_since_loud"), -1.0)
        sound_now = 0.0 <= since_loud < 10.0

        if zero_run > SILENCE_SECONDS and now - self._last_reconnect_at > 600.0:
            self._last_reconnect_at = now
            log.warning("watchdog_dead_device zero_run_s=%.1f action=capture_reconnect", zero_run)
            try:
                self._capture.force_reconnect()
            except Exception as exc:  # noqa: BLE001
                log.error("watchdog_reconnect_failed error=%r", exc)
            return

        # Errors inside the recogniser were counted and never read, so a pipeline
        # where every block failed looked exactly like a healthy silent one: chunks
        # stayed at zero and this check never fired.
        errors = int(worker.get("errors") or 0)
        if errors > self._last_worker_errors:
            grown = errors - self._last_worker_errors
            self._last_worker_errors = errors
            if since_emit > STALL_SECONDS or since_emit < 0:
                log.error(
                    "watchdog_recognition_errors new_errors=%d total=%d since_emit_s=%.1f action=pipeline_restart",
                    grown,
                    errors,
                    since_emit,
                )
                self._safe_restart("recognition_errors")
                return

        dropped = int(capture.get("dropped") or 0)
        if dropped > self._last_capture_dropped:
            log.warning(
                "watchdog_audio_blocks_dropped new=%d total=%d action=stream_reset_on_gap",
                dropped - self._last_capture_dropped,
                dropped,
            )
            self._last_capture_dropped = dropped

        if sound_now and since_emit > STALL_SECONDS and worker.get("chunks", 0) > 0:
            log.error(
                "watchdog_stalled since_emit_s=%.1f chunks=%s action=pipeline_restart",
                since_emit,
                worker.get("chunks"),
            )
            self._safe_restart("stalled")

    def _restart_delay(self) -> float:
        """Gap before the next restart attempt: 60 s, then 120, 300, 600 s."""
        if self._restarts <= 1:
            return RESTART_MIN_INTERVAL
        return min(RESTART_MAX_INTERVAL, RESTART_MIN_INTERVAL * (2 ** (self._restarts - 1)))

    def _safe_restart(self, reason: str) -> None:
        now = time.monotonic()
        if self._restarts and now - self._last_restart_at > RESTART_FORGIVE_SECONDS:
            log.info("pipeline_restart_counter_reset quiet_s=%.0f", now - self._last_restart_at)
            self._restarts = 0
        delay = self._restart_delay()
        if self._restarts and now - self._last_restart_at < delay:
            log.warning(
                "pipeline_restart_skipped reason=too_soon last=%.0fs_ago delay_s=%.0f",
                now - self._last_restart_at,
                delay,
            )
            return
        self._last_restart_at = now
        self._restarts += 1
        log.warning("pipeline_restart reason=%s attempt=%d", reason, self._restarts)
        # Blink the tray icon while recovering, the same way model loading does.
        self._pulse_for(3000)
        try:
            self._restart_pipeline()
        except Exception as exc:  # noqa: BLE001
            # Retry after the same growing delay: a five-second retry was always refused
            # by the interval check, which left a failed restart with no retry at all.
            wait_ms = int(self._restart_delay() * 1000)
            log.error("pipeline_restart_failed error=%r action=retry_in_ms", exc, wait_ms)
            QTimer.singleShot(wait_ms, self._retry_restart)

    def _retry_restart(self) -> None:
        """Deferred retry: never restart the pipeline while the app is shutting down."""
        if self._stopping:
            log.info("pipeline_retry_skipped reason=stopping")
            return
        self._safe_restart("retry")

    # ------------------------------------------------------------------ menu
    def _build_menu(self) -> None:
        menu = QMenu()
        self._act_toggle = QAction("Включить субтитры", self)
        self._act_toggle.triggered.connect(self._toggle_captions)
        menu.addAction(self._act_toggle)

        act_settings = QAction("Настройки", self)
        act_settings.triggered.connect(self.open_settings)
        menu.addAction(act_settings)

        menu.addSeparator()
        act_quit = QAction("Выход", self)
        act_quit.triggered.connect(self.shutdown)
        menu.addAction(act_quit)
        self.tray.setContextMenu(menu)

    def _toggle_captions(self) -> None:
        visible = not self.overlay.captions_visible()
        dialog_open = self._dialog is not None and self._dialog.isVisible()
        self.overlay.set_captions_visible(visible, keep_visible=dialog_open)
        if not visible and self._worker is not None:
            self._worker.request_clear()
        self._update_status()
        log.debug("captions_toggled visible=%s", visible)

    def _open_log(self) -> None:
        """Open the log in the default viewer, creating it when it is not there yet."""
        log_path = paths.app_data_dir() / "app.log"
        try:
            if not log_path.exists():
                # Notepad on a missing file does nothing visible, which looks like a dead
                # button. An empty file opens and the user sees an empty log instead.
                log_path.parent.mkdir(parents=True, exist_ok=True)
                log_path.touch()
                log.info("log_file_created path=%s", log_path)
            os.startfile(str(log_path))  # noqa: S606
        except OSError as exc:
            log.error("log_open_failed path=%s error=%r", log_path, exc)

    # -------------------------------------------------------------- settings
    def open_settings(self, page: int | None = None) -> None:
        if self._dialog is not None and self._dialog.isVisible():
            if page is not None:
                self._dialog.show_page(page)
            self._dialog.raise_()
            self._dialog.activateWindow()
            return
        self._snapshot = self._settings.copy()
        self._dialog = SettingsDialog(
            self._settings,
            on_change=self._preview_settings,
            on_apply=self._apply_settings,
            on_edit_box=self._start_edit_mode,
        )
        self._dialog.rejected.connect(self._on_settings_cancelled)
        self._dialog.finished.connect(self._on_settings_closed)
        self.overlay.set_preview(True)
        self._dialog.show()
        if page is not None:
            self._dialog.show_page(page)
        # Without an explicit raise the first open can stay behind other windows.
        self._dialog.raise_()
        self._dialog.activateWindow()
        log.debug("settings_dialog_opened")

    def _on_settings_closed(self, _result: int) -> None:
        # A preview scheduled 40 ms ago may still be in flight when the dialog is
        # closed with Esc or the cross: without this the overlay applied settings the
        # user had just cancelled.
        self._preview_timer.stop()
        self._pending_settings = None
        self.overlay.set_preview(False)
        if self._worker is not None:
            self._worker.request_clear()
        log.debug("settings_dialog_closed")

    def _preview_settings(self, settings: Settings) -> None:
        """Coalesce rapid changes: apply the preview at most every 40 ms."""
        self._pending_settings = settings
        if not self._preview_timer.isActive():
            self._preview_timer.start(40)

    def _flush_preview(self) -> None:
        if self._pending_settings is not None:
            self.overlay.apply_settings(self._pending_settings)
            self._pending_settings = None

    def _apply_settings(self, settings: Settings) -> None:
        self._pending_settings = None
        self._preview_timer.stop()
        previous = self._snapshot
        self._settings = settings
        self._snapshot = settings.copy()
        self.overlay.apply_settings(settings)
        save_settings(settings)
        if settings.behaviour.autostart != previous.behaviour.autostart:
            ok = paths.set_autostart(settings.behaviour.autostart)
            log.info("autostart_changed enabled=%s ok=%s", settings.behaviour.autostart, ok)
            actual = paths.autostart_enabled()
            if actual is not None and actual != settings.behaviour.autostart:
                # The Run key did not take the value (policy, permissions, another copy of
                # the app): keep the checkbox honest instead of promising autostart.
                log.warning(
                    "autostart_not_applied requested=%s actual=%s action=revert",
                    settings.behaviour.autostart,
                    actual,
                )
                settings.behaviour.autostart = actual
                save_settings(settings)
        pipeline_changed = (
            settings.audio.threads != previous.audio.threads or settings.audio.device != previous.audio.device
        )
        if pipeline_changed:
            log.info(
                "audio_settings_changed device=%r threads=%d action=pipeline_restart",
                settings.audio.device,
                settings.audio.threads,
            )
            self._restart_pipeline()

    def _on_settings_cancelled(self) -> None:
        # Preview only ever touches the overlay: the capture device and the thread count
        # are applied in _apply_settings, so cancelling has nothing else to undo.
        self._preview_timer.stop()
        self._pending_settings = None
        self._settings = self._snapshot
        self.overlay.apply_settings(self._settings)
        log.debug("settings_dialog_cancelled action=revert")

    def _on_geometry_edited(self) -> None:
        # Only the plate position belongs to this action. save_settings(self._settings)
        # also wrote the dialog preview values, so Cancel could not undo them.
        save_geometry(self._settings)

    def _start_edit_mode(self) -> None:
        if self._dialog is not None and self._dialog.isVisible():
            self._reopen_settings_after_edit = True
            self._dialog.hide()
        self.overlay.begin_edit_mode()

    def _after_edit_mode(self) -> None:
        if self._reopen_settings_after_edit:
            self._reopen_settings_after_edit = False
            page = self._dialog.current_page() if self._dialog is not None else 1
            if self._dialog is not None:
                self._dialog.reload_from_settings(self._settings)
            self.open_settings(page=page)

    # ----------------------------------------------------------------- start
    def start(self) -> None:
        """Start loading the model in the background; the tray is usable immediately."""
        self._loading = True
        self._pulse.start()
        threading.Thread(target=self._load_model, name="model-loader", daemon=True).start()

    def _pulse_tick(self, opacity: float) -> None:
        if not self._loading:
            return
        self.tray.setIcon(make_icon(self.overlay.captions_visible(), "", float(opacity)))

    def _pulse_for(self, ms: int) -> None:
        """Blink the tray icon for a while: the only sign of a soft restart."""
        self._loading = True
        self._pulse.start()
        QTimer.singleShot(int(ms), self._stop_pulse)

    def _stop_pulse(self) -> None:
        self._loading = False
        self._pulse.stop()
        # The pulse left a semi-transparent icon, which the cache does not know about.
        self._icon_state = None
        self._update_status()

    def _load_model(self) -> None:
        if self._load_inflight:
            log.info("model_load_skipped reason=already_inflight")
            return
        self._load_inflight = True
        try:
            model = paths.model_dir()
            log.debug("model_dir path=%s", model)
            try:
                engine = TOneStreamingASR(model, num_threads=self._settings.audio.threads)
            except Exception as exc:  # noqa: BLE001
                log.error("model_load_failed error=%r action=retry_later", exc)
                self.pipeline_failed.emit(str(exc))
                return
            if self._stopping:
                log.info("model_loaded_but_stopping")
                return
            self._asr = engine
            self._load_failed = False
            self._load_attempts = 0
            self.pipeline_ready.emit()
        finally:
            self._load_inflight = False

    def _on_pipeline_ready(self) -> None:
        self._stop_pulse()
        self.overlay.set_ready(True)
        self._start_pipeline()
        if self._restart_after_load:
            self._restart_after_load = False
            self._restart_pipeline()
        log.info("model_ready device=%r threads=%d", self._settings.audio.device, self._settings.audio.threads)

    def _on_pipeline_failed(self, message: str) -> None:
        self._stop_pulse()
        self._load_failed = True
        self._load_attempts += 1
        self.tray.setIcon(make_icon(False))
        self._icon_state = None
        self.tray.setToolTip(paths.APP_DISPLAY_NAME)
        delay_ms = int(min(LOAD_RETRY_MAX_MS, LOAD_RETRY_MIN_MS * 2 ** (self._load_attempts - 1)))
        log.error(
            "model_load_retry_scheduled attempt=%d delay_s=%.0f", self._load_attempts, delay_ms / 1000.0
        )
        if self._load_attempts == 1:
            QMessageBox.critical(None, paths.APP_DISPLAY_NAME, f"Не удалось загрузить модель:\n{message}")
        else:
            self._notify("Модель не загрузилась", f"Повторю попытку через {int(delay_ms / 1000)} с.")
        QTimer.singleShot(delay_ms, self._retry_load_model)

    def _retry_load_model(self) -> None:
        """A single failed load must not leave the app dead until a manual restart."""
        if self._stopping or self._asr is not None or self._load_inflight:
            return
        log.info("model_load_retry attempt=%d", self._load_attempts + 1)
        threading.Thread(target=self._load_model, name="model-loader-retry", daemon=True).start()

    def _start_pipeline(self) -> None:
        if self._asr is None:
            return
        self._capture = LoopbackCapture(self._audio_queue, device=self._settings.audio.device)
        self._capture.start()
        self._worker = RecognitionWorker(
            self._asr,
            self._audio_queue,
            self.text_ready.emit,
            lambda: False,
            highlight_seconds=lambda: self._settings.behaviour.highlight_seconds,
        )
        self._worker.start()
        # Fresh threads start their counters at zero: keeping the old baselines hid
        # every later error and dropped block from the watchdog.
        self._last_worker_errors = 0
        self._last_capture_dropped = 0

    def _restart_pipeline(self) -> None:
        """Restart on a helper thread: joining stuck threads froze the GUI for seconds."""
        if self._restart_thread is not None and self._restart_thread.is_alive():
            log.info("pipeline_restart_skipped reason=already_running")
            return
        self._restart_thread = threading.Thread(
            target=self._restart_pipeline_now, name="pipeline-restart", daemon=True
        )
        self._restart_thread.start()

    def _on_pipeline_restarted(self) -> None:
        self._update_status()

    def _on_relaunch_requested(self, reason: str) -> None:
        log.warning("relaunch_requested reason=%s", reason)
        self._relaunch()

    def _restart_pipeline_now(self) -> None:
        with self._pipeline_lock:
            try:
                stuck = []
                if self._worker is not None:
                    self._worker.stop()
                    self._worker.join(timeout=3.0)
                    if self._worker.is_alive():
                        stuck.append("asr")
                if self._capture is not None:
                    self._capture.stop()
                    self._capture.join(timeout=3.0)
                    if self._capture.is_alive():
                        stuck.append("capture")
                if stuck:
                    # A second pipeline on top of live threads would process every chunk
                    # twice: report, and escalate to a full relaunch — a thread stuck in
                    # native code cannot be joined or killed from Python.
                    self._stuck_restarts += 1
                    log.error(
                        "pipeline_restart_blocked reason=threads_alive stuck=%s attempt=%d",
                        ",".join(stuck),
                        self._stuck_restarts,
                    )
                    if self._stuck_restarts >= 2:
                        log.error("pipeline_restart_escalate action=relaunch reason=threads_wont_stop")
                        # Shutdown must happen on the GUI thread, not in this helper.
                        self.relaunch_requested.emit("threads_wont_stop")
                    return
                self._stuck_restarts = 0
                while not self._audio_queue.empty():
                    self._audio_queue.get_nowait()
                self._start_pipeline()
                log.info("pipeline_restarted device=%r threads=%d", self._settings.audio.device, self._settings.audio.threads)
                self.pipeline_restarted.emit()
            except Exception as exc:  # noqa: BLE001
                log.error("pipeline_restart_failed error=%r action=retry_in_5s", exc)
                QTimer.singleShot(5000, self._retry_restart)

    def _on_idle_clear(self) -> None:
        if self._worker is not None and not self.overlay.preview_mode():
            self._worker.request_clear()

    def _log_pipeline_stats(self) -> None:
        """Once a minute: what the pipeline actually sees.

        An empty box has two very different causes that look the same from outside:
        no audio on the device at all, or audio that recognition throws away. Without
        these numbers a support question "субтитры не появляются" cannot be answered.
        """
        capture = self._capture
        worker = self._worker
        if capture is None or worker is None:
            return
        try:
            cap = capture.stats()
            rec = worker.stats()
        except Exception as exc:  # noqa: BLE001
            log.warning("pipeline_stats_failed error=%r", exc)
            return
        log.info(
            "pipeline_stats blocks=%s silent=%s dropped=%s capture=%s"
            " zero_run_s=%s since_audio_s=%s chunks=%s emitted=%s errors=%s text_len=%s",
            cap.get("blocks"),
            cap.get("silent_blocks"),
            cap.get("dropped"),
            cap.get("state"),
            cap.get("zero_run_seconds"),
            cap.get("seconds_since_audio"),
            rec.get("chunks"),
            rec.get("emitted"),
            rec.get("errors"),
            rec.get("text_len"),
        )

    def _update_status(self) -> None:
        self._stats_tick += 1
        if self._stats_tick % 30 == 0:
            self._log_pipeline_stats()
        visible = self.overlay.captions_visible()
        kind, text = self._status_kind()
        self._act_toggle.setText("Выключить субтитры" if visible else "Включить субтитры")
        # A dead pipeline forces the off icon: the tray must not claim captions that are
        # not coming. The status text used to be computed and thrown away, so an error was
        # invisible until the user opened the log.
        icon_on = visible and kind != "danger"
        status = kind if kind in ("warn", "danger") else ""
        state = (icon_on, status, text)
        if not self._loading and state != self._icon_state:
            self._icon_state = state
            self.tray.setIcon(make_icon(icon_on, status))

    def shutdown(self) -> None:
        self._stopping = True
        self._pulse.stop()
        log.info("app_stopping")
        if self._capture is not None:
            self._capture.stop()
        if self._worker is not None:
            self._worker.stop()
        # Both threads must be gone before Qt tears the objects down, otherwise a
        # late emit from the worker hits a destroyed overlay and the app crashes on exit.
        for thread, name in ((self._worker, "asr"), (self._capture, "capture")):
            if thread is None:
                continue
            thread.join(timeout=2.0)
            if thread.is_alive():
                log.warning("app_stop_thread_alive thread=%s timeout_s=2.0", name)
        self.tray.hide()
        self._app.quit()
