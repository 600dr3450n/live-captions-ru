"""Recognition worker: audio chunks in, stabilised captions out.

The captions are one continuous stream of words. There is deliberately no notion
of a phrase here: the model's idea of where a sentence ends has nothing to do with
what the viewer needs, and closing a phrase on a pause made the text jump while the
speaker was still going. Words are aged instead — the UI dims a word once it is
older than the highlight window from the settings, whatever line it sits on.
"""
from __future__ import annotations

import logging
import queue
import threading
import time

import numpy as np

from asr import TOneStreamingASR
from config import (
    MAX_STREAM_TEXT,
    MIN_EMIT_INTERVAL,
    REWRITE_MIN_CHARS,
    REWRITE_RATIO,
    TAIL_PAD_SECONDS,
    WORD_SETTLE_SECONDS,
)

log = logging.getLogger(__name__)


class RecognitionWorker(threading.Thread):
    """Consumes audio chunks and emits caption text for the UI thread."""

    def __init__(self, recognizer: TOneStreamingASR, audio_queue: "queue.Queue", on_text, is_paused, highlight_seconds=None) -> None:
        super().__init__(name="asr", daemon=True)
        self._recognizer = recognizer
        self._audio = audio_queue
        self._on_text = on_text
        self._is_paused = is_paused
        self._highlight_seconds = highlight_seconds or (lambda: 2.0)
        self._stop_event = threading.Event()
        self.clear_requested = threading.Event()
        self._word_times: list[float] = []
        self._last_text = ""
        self._last_change_at = 0.0
        self._chunks = 0
        self._emitted = 0
        self._errors = 0
        self._last_emit_at = 0.0
        self._text_len = 0
        self._stream_text_len = 0
        self._poll_index = 0
        # stats() runs on the GUI thread while this thread writes the counters.
        self._stats_lock = threading.Lock()

    def request_clear(self) -> None:
        self.clear_requested.set()

    def _highlight_range(self, text: str) -> tuple[int, int]:
        """Words recognised inside the highlight window: they stay bright."""
        now = time.monotonic()
        if text != self._last_text:
            self._last_text = text
            self._last_change_at = now
        idle = now - self._last_change_at if self._last_change_at else 0.0

        words = text.split()
        complete = len(words)
        if words and not text.endswith(" ") and idle < WORD_SETTLE_SECONDS:
            complete -= 1
        complete = max(0, complete)

        if complete > len(self._word_times):
            for _ in range(complete - len(self._word_times)):
                self._word_times.append(now)
        elif complete < len(self._word_times):
            del self._word_times[complete:]
        if complete == 0:
            return 0, 0

        window = max(0.5, float(self._highlight_seconds()))
        start = complete
        while start - 1 >= 0 and now - self._word_times[start - 1] <= window:
            start -= 1
        return start, complete

    def stop(self) -> None:
        self._stop_event.set()

    def stats(self) -> dict:
        """Consistent snapshot for the watchdog: counters are written by this thread."""
        now = time.monotonic()
        with self._stats_lock:
            chunks = self._chunks
            emitted = self._emitted
            errors = self._errors
            text_len = self._text_len
            stream_text_len = self._stream_text_len
            last_emit_at = self._last_emit_at
        return {
            "alive": self.is_alive(),
            "chunks": chunks,
            "emitted": emitted,
            "errors": errors,
            "text_len": text_len,
            "stream_text_len": stream_text_len,
            "seconds_since_emit": round(now - last_emit_at, 1) if last_emit_at else -1.0,
        }

    def _flush_tail(self, stream, rate):
        """Feed trailing silence so the model finishes the last word.

        Returns the text the model produced, or None when there is nothing to do.
        """
        if stream is None or not rate:
            return None
        pad = np.zeros(int(rate * TAIL_PAD_SECONDS), dtype=np.float32)
        try:
            return self._recognizer.feed(stream, pad, rate)
        except Exception as exc:  # noqa: BLE001
            log.warning("tail_flush_failed error=%r action=ignore", exc)
            return None

    def _clear(self, stream) -> None:
        """Drop the visible text together with the model hypothesis behind it.

        Clearing only the local variables left stream.text intact, so the very next
        block republished the whole old line and the box flickered instead of
        staying empty.
        """
        if stream is not None:
            self._recognizer.reset(stream)
        log.debug("captions_cleared")
        self._on_text("", 0, 0, 0)

    def _reset_words(self) -> None:
        self._word_times = []
        self._last_text = ""
        self._last_change_at = 0.0

    def _publish(self, text: str, start: int, complete: int) -> None:
        # _chunks counts audio blocks handled by the loop and _stream_text_len the
        # model hypothesis: neither may be written here, or stats() lies.
        with self._stats_lock:
            self._text_len = len(text)
            self._emitted += 1
            self._last_emit_at = time.monotonic()
        self._on_text(text, complete, start, complete)

    def run(self) -> None:
        """Never let an unexpected exception kill the thread silently."""
        try:
            self._run_loop()
        except Exception as exc:  # noqa: BLE001
            log.error("recognition_worker_crashed error=%r action=stop", exc)
            with self._stats_lock:
                self._errors += 1
            self._stop_event.set()

    def _run_loop(self) -> None:
        stream = self._recognizer.create_stream()
        text = ""
        paused_flushed = False
        rate: int | None = None
        last_text_state = None
        last_start = -1
        last_emit = 0.0
        prev_len = 0

        while not self._stop_event.is_set():
            # Clear before waiting for audio: with a dead capture the queue stays
            # empty and a clear request would otherwise hang until the next block.
            if self.clear_requested.is_set():
                self.clear_requested.clear()
                self._clear(stream)
                text = ""
                prev_len = 0
                last_text_state = None
            try:
                chunk = self._audio.get(timeout=0.2)
            except queue.Empty:
                continue
            if getattr(chunk, "resumes_after_gap", False):
                # Blocks were dropped (queue overflow): the model state no longer
                # matches the audio, so the hypothesis is restarted instead of being
                # glued across the hole.
                log.warning("audio_gap action=stream_reset dropped_blocks_seen")
                self._recognizer.reset(stream)
                text = ""
                prev_len = 0
                last_text_state = None
                self._reset_words()
            if self._is_paused():
                if not paused_flushed:
                    paused_flushed = True
                    flushed = self._flush_tail(stream, rate)
                    if flushed is not None and flushed != text:
                        text = flushed
                        phrase_words = len(text.split())
                        self._publish(text, 0, phrase_words)
                        log.debug("tail_flushed reason=paused chars=%d", len(text))
                continue
            paused_flushed = False
            if rate is not None and chunk.rate != rate:
                log.debug("audio_rate_changed previous=%d current=%d action=stream_recreated", rate, chunk.rate)
                self._flush_tail(stream, rate)
                stream = self._recognizer.create_stream()
                text = ""
                prev_len = 0
                self._reset_words()
                last_text_state = None
            rate = chunk.rate

            try:
                self._poll_index += 1
                text = self._recognizer.feed(stream, chunk.samples, chunk.rate)
            except Exception as exc:  # noqa: BLE001
                log.error("recognition_failed error=%r action=stream_recreated", exc)
                with self._stats_lock:
                    # The block was consumed either way: counting only successes
                    # left the watchdog blind when every block failed.
                    self._chunks += 1
                    self._errors += 1
                stream = self._recognizer.create_stream()
                text = ""
                prev_len = 0
                self._reset_words()
                continue

            if prev_len and len(text) < prev_len * REWRITE_RATIO and prev_len - len(text) > REWRITE_MIN_CHARS:
                log.info(
                    "hypothesis_rewritten previous_len=%d current_len=%d action=stream_reset",
                    prev_len,
                    len(text),
                )
                stream = self._recognizer.create_stream()
                text = ""
                prev_len = 0
                self._reset_words()
                last_text_state = None
                continue
            prev_len = len(text)

            start, complete = self._highlight_range(text)
            text_state = (text, complete)
            now = time.monotonic()
            with self._stats_lock:
                self._chunks += 1
                self._text_len = len(text)
                self._stream_text_len = len(text)
            if text_state != last_text_state:
                last_text_state = text_state
                last_start = start
                last_emit = now
                with self._stats_lock:
                    self._emitted += 1
                    self._last_emit_at = now
                self._on_text(text, complete, start, complete)
            elif start != last_start and (now - last_emit) >= MIN_EMIT_INTERVAL:
                last_start = start
                last_emit = now
                with self._stats_lock:
                    self._emitted += 1
                    self._last_emit_at = now
                self._on_text(text, complete, start, complete)

            # The model state grows without bound, so it is recreated at this size.
            # Publishing the empty string afterwards cleared the plate in the middle of
            # a phrase: the last state is marked as "already empty" instead, so the
            # previous line stays on screen until the next real text replaces it.
            if len(text) > MAX_STREAM_TEXT:
                log.debug("stream_reset reason=long_text text_len=%d action=keep_visible", len(text))
                stream = self._recognizer.create_stream()
                text = ""
                prev_len = 0
                self._reset_words()
                last_text_state = ("", 0)

        tail = self._flush_tail(stream, rate)
        if tail is not None and tail != text:
            self._publish(tail, 0, len(tail.split()))
            log.info("tail_flushed reason=stopped added_chars=%d", len(tail) - len(text))
        log.info("recognition_worker_stopped reason=stop_event errors=%d chunks=%d", self._errors, self._chunks)
