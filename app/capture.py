"""Loopback capture of the system output device (everything you hear)."""
from __future__ import annotations

import logging
import queue
import threading
import time
import warnings
from dataclasses import dataclass

import numpy as np
import soundcard as sc

log = logging.getLogger(__name__)

# soundcard warns on every WASAPI gap, which on a busy machine is several times a
# second and floods stderr of a console build. The gaps are harmless: the model
# only needs the samples that did arrive.
warnings.filterwarnings("ignore", message="data discontinuity in recording")

RATE = 48000  # Windows shared-mode mix rate for virtually all output devices
DEVICE_POLL_SECONDS = 2.0
# A device that keeps failing for 20 s is gone, not flaky: spinning forever hides the
# failure from the user instead of letting the watchdog report it.
MAX_CONSECUTIVE_FAILURES = 20
LOUD_PEAK = 0.01  # above this the output counts as audible


@dataclass(frozen=True)
class AudioChunk:
    samples: np.ndarray  # float32 mono, range [-1, 1]
    rate: int
    # True on the first block after the queue overflowed: the model state no longer
    # matches the audio, so the worker restarts the hypothesis instead of gluing it.
    resumes_after_gap: bool = False


class LoopbackCapture(threading.Thread):
    """Listens to the system output device.

    device="" follows the default output device; if Windows switches it (for example
    Bluetooth from A2DP to Hands-Free when a call starts), the stream reconnects itself.
    """

    def __init__(self, out_queue: "queue.Queue[AudioChunk]", device: str = "", block_seconds: float = 0.02) -> None:
        super().__init__(name="capture", daemon=True)
        self._queue = out_queue
        self._preferred_device = device
        self._stop_event = threading.Event()
        self._block_seconds = block_seconds
        self._state = "starting"
        self._device_name = ""
        self._blocks = 0
        self._silent_blocks = 0
        self._dropped = 0
        self._last_audio_at = 0.0
        self._device_failures = 0
        self._silent_since = 0.0
        self._last_loud_at = 0.0
        self._reconnect_requested = False
        self._gap_pending = False
        # Last seen system default output. Device changes are detected against this,
        # never against the captured device: with a pinned device the two differ by
        # definition and the recorder was reopened on every poll.
        self._observed_default_id = ""
        self._observed_default_name = ""
        # stats() is polled by the GUI thread while this thread writes the counters.
        self._stats_lock = threading.Lock()

    @property
    def state(self) -> str:
        return self._state

    @property
    def device_name(self) -> str:
        return self._device_name

    def stats(self) -> dict:
        """Consistent snapshot for the watchdog: counters are written by the capture thread."""
        now = time.monotonic()
        with self._stats_lock:
            state = self._state
            device = self._device_name
            blocks = self._blocks
            silent_blocks = self._silent_blocks
            dropped = self._dropped
            device_failures = self._device_failures
            last_audio_at = self._last_audio_at
            silent_since = self._silent_since
            last_loud_at = self._last_loud_at
        return {
            "state": state,
            "device": device,
            "blocks": blocks,
            "silent_blocks": silent_blocks,
            "dropped": dropped,
            "device_failures": device_failures,
            "seconds_since_audio": round(now - last_audio_at, 1) if last_audio_at else -1.0,
            "zero_run_seconds": round(now - silent_since, 1) if silent_since else 0.0,
            "seconds_since_loud": round(now - last_loud_at, 1) if last_loud_at else -1.0,
            "alive": self.is_alive(),
        }

    def force_reconnect(self) -> None:
        log.warning("capture_force_reconnect device=%r", self._device_name)
        with self._stats_lock:
            self._state = "reconnecting"
            self._device_failures = 0
        self._reconnect_requested = True

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        failures = 0
        while not self._stop_event.is_set():
            try:
                self._capture_until_device_changes()
                if failures:
                    # A recovered stream starts after a hole in the audio.
                    self._gap_pending = True
                failures = 0
            except Exception as exc:  # noqa: BLE001
                failures += 1
                with self._stats_lock:
                    self._state = "error"
                if failures >= MAX_CONSECUTIVE_FAILURES:
                    # Give up instead of spinning silently: alive=False makes the
                    # watchdog show "распознавание остановлено" and restart the pipeline.
                    with self._stats_lock:
                        self._state = "failed"
                    log.error("capture_failed_permanently error=%r failures=%d action=stop", exc, failures)
                    break
                # Back off instead of hammering the device: every retry opens a new COM
                # recorder, and soundcard leaks a few objects when Start/Stop fails.
                retry_in = min(10.0, 1.0 * failures)
                log.warning(
                    "capture_interrupted error=%r failures=%d action=retry retry_in_s=%.0f",
                    exc,
                    failures,
                    retry_in,
                )
                self._stop_event.wait(retry_in)
        with self._stats_lock:
            if self._state != "failed":
                self._state = "stopped"
            final_state = self._state
        log.info("capture_stopped device=%r state=%s", self._device_name, final_state)

    def _pick_speaker(self):
        if self._preferred_device:
            for speaker in sc.all_speakers():
                if speaker.name == self._preferred_device:
                    return speaker
            log.warning("capture_device_not_found device=%r action=use_default", self._preferred_device)
        return sc.default_speaker()

    def _capture_until_device_changes(self) -> None:
        speaker = self._pick_speaker()
        device_id = speaker.id
        mic = sc.get_microphone(id=speaker.name, include_loopback=True)
        frames = max(int(RATE * self._block_seconds), 160)
        # Some endpoints (Bluetooth, HDMI, USB) reject a period shorter than their
        # own minimum, and Initialize then fails twenty times in a row. Ask the
        # device first and only then fall back to our own block size.
        period = getattr(mic, "deviceperiod", None)
        try:
            if period:
                min_frames = int(float(period[0]) * RATE)
                if min_frames > frames:
                    log.info(
                        "capture_block_size device_min_frames=%d requested=%d action=use_device_min",
                        min_frames,
                        frames,
                    )
                    frames = min_frames
        except (TypeError, ValueError, IndexError) as exc:
            log.debug("capture_device_period_unusable error=%r", exc)
        channels = int(getattr(mic, "channels", 2) or 2)

        self._device_name = speaker.name
        with self._stats_lock:
            self._state = "running"
        self._reconnect_requested = False
        log.info("capture_started device=%r rate=%d channels=%d block_frames=%d", speaker.name, RATE, channels, frames)

        next_check = time.monotonic() + DEVICE_POLL_SECONDS
        with mic.recorder(samplerate=RATE, channels=channels, blocksize=frames) as recorder:
            while not self._stop_event.is_set():
                try:
                    block = recorder.record(numframes=frames)
                except Exception as exc:  # noqa: BLE001
                    # Log the real cause here: soundcard 0.4.6 raises again from its own
                    # __exit__ (COM release on a dead endpoint) and that second error is
                    # what reaches run(), hiding this one.
                    log.error("capture_read_failed error=%r device=%r", exc, speaker.name)
                    raise
                self._push(self._to_chunk(block))
                if getattr(self, "_reconnect_requested", False):
                    log.warning("capture_reconnect_requested device=%r", self._device_name)
                    with self._stats_lock:
                        self._state = "device_changed"
                    # The audio stream is about to break: the worker must reset the model
                    # hypothesis on the first block after it, or it glues words together.
                    self._gap_pending = True
                    return
                if time.monotonic() >= next_check:
                    next_check = time.monotonic() + DEVICE_POLL_SECONDS
                    if self._output_device_changed(device_id, speaker.name):
                        log.info("output_device_changed previous=%r action=reconnect", self._device_name)
                        with self._stats_lock:
                            self._state = "device_changed"
                        self._gap_pending = True
                        return

    def _output_device_changed(self, previous_id: str, previous_name: str) -> bool:
        try:
            self._device_failures = 0
            if self._preferred_device:
                # Pinned device: it is not the system default by design, so only its
                # disappearance means "reconnect", not a difference from the default.
                names = {speaker.name for speaker in sc.all_speakers()}
                if self._preferred_device in names:
                    return False
                log.warning("capture_pinned_device_lost device=%r action=reconnect", self._preferred_device)
                return True
            current = sc.default_speaker()
            if not self._observed_default_id:
                self._observed_default_id = current.id
                self._observed_default_name = current.name
                return current.id != previous_id or current.name != previous_name
            if current.id == self._observed_default_id and current.name == self._observed_default_name:
                return False
            log.info(
                "output_default_changed previous=%r current=%r",
                self._observed_default_name,
                current.name,
            )
            self._observed_default_id = current.id
            self._observed_default_name = current.name
            return True
        except Exception as exc:  # noqa: BLE001
            with self._stats_lock:
                self._device_failures += 1
                failures = self._device_failures
            if failures >= 3:
                log.warning("capture_device_query_failed error=%r action=reconnect", exc)
                return True
            return False

    @staticmethod
    def _to_chunk(block: np.ndarray) -> AudioChunk:
        data = np.asarray(block, dtype=np.float32)
        mono = data.mean(axis=1, dtype=np.float32) if data.ndim == 2 and data.shape[1] > 1 else data.reshape(-1)
        return AudioChunk(mono, RATE)

    def _push(self, chunk: AudioChunk) -> None:
        """Never let the queue grow: drop the oldest block to keep latency flat."""
        peak = float(np.max(np.abs(chunk.samples))) if chunk.samples.size else 0.0
        now = time.monotonic()
        with self._stats_lock:
            self._blocks += 1
            self._last_audio_at = now
            # One threshold for "the output is audible". With two of them the band
            # 1e-6 < peak <= 0.01 moved neither the loud timestamp nor the silence
            # timer, so the watchdog saw a device that is alive but never speaks and
            # no rule (dead device, stall) could ever fire.
            if peak > LOUD_PEAK:
                self._last_loud_at = now
                self._silent_since = 0.0
            else:
                if not self._silent_since:
                    self._silent_since = now
                if peak <= 1e-6:
                    self._silent_blocks += 1
        if self._gap_pending:
            self._gap_pending = False
            chunk = AudioChunk(chunk.samples, chunk.rate, True)
        try:
            self._queue.put_nowait(chunk)
        except queue.Full:
            with self._stats_lock:
                self._dropped += 1
            self._gap_pending = True
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(chunk)
            except queue.Full:
                pass
