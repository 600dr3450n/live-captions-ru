"""Tunable constants shared by the application modules."""
from __future__ import annotations

import os


def _num_env(name: str, default: float) -> float:
    """Allow overriding a tuning constant for tests without editing the build."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


MIN_EMIT_INTERVAL = 0.08  # screen updates at most ~12 times per second
WORD_SETTLE_SECONDS = 0.35  # a word is considered finished after this quiet period
MAX_STREAM_TEXT = 4000  # characters in the model stream before a reset
# A streaming model can rewrite its tail; when the whole hypothesis collapses the
# stream state is worthless and gets recreated. The check is deliberately loose so
# that ordinary tail corrections (a word shorter than the one before) do not count.
REWRITE_RATIO = 0.7  # text shorter than this share of the previous one is a rewrite
REWRITE_MIN_CHARS = 80  # and it has to be shorter by at least this many characters
# The streaming model needs right context to emit the last frames of a word: cut
# the audio mid-word and the tail of the phrase is lost (measured on OpenSTT
# asr_calls_2_val: 47% WER without padding against 21% with it). When capture
# stops, switches device or pauses, this much silence is fed before the stream is
# dropped so the final word is finished.
TAIL_PAD_SECONDS = 0.6
WATCHDOG_SECONDS = _num_env("LIVECAPTIONSRU_WATCHDOG_SECONDS", 5.0)  # liveness check interval
# Pipeline restart cadence. The first attempt may follow a failure after a minute, then
# the gap doubles up to ten minutes: a broken model or a dead device would otherwise
# reload a nine-second model every minute for the whole session.
RESTART_MIN_INTERVAL = _num_env("LIVECAPTIONSRU_RESTART_MIN_INTERVAL", 60.0)
RESTART_MAX_INTERVAL = _num_env("LIVECAPTIONSRU_RESTART_MAX_INTERVAL", 600.0)
# After this long without a restart the counter is treated as fresh again.
RESTART_FORGIVE_SECONDS = _num_env("LIVECAPTIONSRU_RESTART_FORGIVE_SECONDS", 1800.0)
# A failed model load used to leave the app alive but mute until a manual restart.
# Retry on a doubling delay: 15 s, 30 s, 60 s ... capped at five minutes.
LOAD_RETRY_MIN_MS = _num_env("LIVECAPTIONSRU_LOAD_RETRY_MIN_MS", 15_000.0)
LOAD_RETRY_MAX_MS = _num_env("LIVECAPTIONSRU_LOAD_RETRY_MAX_MS", 300_000.0)
# Live speech produces text every 1-3 s (measured on real calls), so a minute
# without a single result while the microphone hears sound means the pipeline
# is stuck, not that the room is quiet.
STALL_SECONDS = _num_env("LIVECAPTIONSRU_STALL_SECONDS", 60.0)  # sound but no text: restart
SILENCE_SECONDS = _num_env("LIVECAPTIONSRU_SILENCE_SECONDS", 300.0)  # silent loopback: reopen device
# Measured on 1.0.1 (fp32 model, 2 threads): 592 MB private commit and 310-380 MB
# working set, flat over a 9 minute run. There is no leak to manage, so the only
# memory rule left is an emergency valve: 1024 MB of working set is ~2.7x the
# observed peak, high enough never to fire on a healthy run, low enough to catch
# a runaway before Windows starts swapping.
RSS_LIMIT_MB = _num_env("LIVECAPTIONSRU_RSS_LIMIT_MB", 1024.0)
# A relaunch because of memory happens at most this many times in a row: the counter
# travels to the new process in ENV_RECYCLE_COUNT. Otherwise a threshold lower than the
# real footprint turns the app into a restart loop that never shows a caption.
RSS_RECYCLE_MAX = int(_num_env("LIVECAPTIONSRU_RSS_RECYCLE_MAX", 2.0))
ENV_RECYCLE_COUNT = "LIVECAPTIONSRU_RECYCLE_COUNT"
RELAUNCH_WAIT_ARG = "--relaunch-wait"
TAKEOVER_ARG = "--takeover"
# How long a relaunched copy waits for the previous one to release the single-instance
# mutex. The old process is shutting down on purpose, so this only has to cover a slow
# model teardown; longer than that means it hung and the new copy must not join in.
TAKEOVER_WAIT_SECONDS = _num_env("LIVECAPTIONSRU_TAKEOVER_WAIT_SECONDS", 20.0)
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
MUTEX_NAME = "Local\\LiveCaptionsRU_SingleInstance"
ENV_CAPTURE_EXCLUSION = "LIVECAPTIONSRU_CAPTURE_EXCLUSION"
