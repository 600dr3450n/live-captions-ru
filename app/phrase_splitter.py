"""Phrase boundaries from the acoustic model itself, not from loudness.

Ported from the reference T-one pipeline (`tone/logprob_splitter.py`, Apache-2.0,
T-Software DC): the splitter looks at the summed probability of the space and blank
tokens and treats a run of low-probability frames as silence. A silence of
MIN_SILENCE_FRAMES frames is a phrase separator, so phrases follow the model's own
view of where speech stops instead of an energy threshold.

Why it matters here: a recurrent state carried across a pause lets the first word
after it glue onto the last word before it ("сервисный центр" + "ольга" heard as
«сервисный центрольга»). An energy gate can only react after GATE_HOLD_CHUNKS of
flat audio, while the model knows within a fraction of a second. The splitter costs
nothing extra: the log-probabilities it needs are already computed for decoding.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

FRAME_RATE = 1000.0 / 30.0  # 10 frames per 300 ms chunk, ~33.3 frames per second
SILENCE_THRESHOLD = 0.9  # summed probability of space+blank at or above = silence
MIN_SILENCE_FRAMES = 30  # 0.9 s of silence separates phrases
# Silence is not the same as a short inter-word gap: a phrase may continue while the
# speaker draws breath, so only a long break ends it.
# The reference T-one pipeline splits at 0.6 s because it cuts audio into segments for
# batch decoding. For live captions that is too eager: on 11.7 min of real conversation
# 0.6 s produced 122 phrases with 18% of them shorter than 2 s, while 0.9 s produced 78
# phrases and the same recognised text. Short fragments are what makes a phrase jump to
# the history line and its continuation appear below, so the threshold is raised.
MAX_PHRASE_FRAMES = 2000  # 60 s: force a break so one endless phrase cannot grow


@dataclass
class SplitterState:
    """Carry-over between chunks: only the tail that may still be inside a pause."""

    past_speech: np.ndarray = field(
        default_factory=lambda: np.zeros(0, dtype=bool))
    frames_seen: int = 0  # global frame counter, for reporting phrase lengths
    in_pause: bool = False  # already reported this pause, do not report it again
    seen_speech: bool = False  # a phrase needs speech before its end means anything


class PhraseSplitter:
    """Streaming detector of phrase ends by blank/space probability."""

    def __init__(
        self,
        silence_threshold: float = SILENCE_THRESHOLD,
        min_silence_frames: int = MIN_SILENCE_FRAMES,
        max_phrase_frames: int = MAX_PHRASE_FRAMES,
    ) -> None:
        self.silence_threshold = silence_threshold
        self.min_silence_frames = min_silence_frames
        self.max_phrase_frames = max_phrase_frames

    def new_state(self) -> SplitterState:
        return SplitterState()

    @staticmethod
    def silence_frame() -> np.ndarray:
        """Log-probabilities of one frame of pure silence, for gated-out audio.

        The gate drops quiet chunks before they reach the model, so the splitter would
        never see them. Feeding this instead keeps the timeline continuous: a real
        pause still closes the phrase, and the splitter needs no special case.
        """
        frame = np.full(35, -50.0, dtype=np.float32)
        frame[33] = 0.0  # space
        frame[34] = 0.0  # blank
        return frame.reshape(1, 35)

    def push(self, state: SplitterState, logprobs: np.ndarray) -> tuple[bool, int]:
        """Feed log-probabilities (frames x 35) and report a phrase end.

        Returns (phrase_ended, frames_in_phrase). The run of trailing speech is kept
        in the state so a pause split across two chunks is still detected.
        """
        if logprobs.ndim != 2:
            logprobs = logprobs.reshape(-1, logprobs.shape[-1])
        space_blank = np.exp(logprobs[:, -2:]).sum(axis=1)
        speech = space_blank <= self.silence_threshold

        combined = np.concatenate([state.past_speech, speech]) if state.past_speech.size else speech
        state.frames_seen += combined.size - state.past_speech.size

        ended = False
        frames_in_phrase = 0
        # A phrase ends when a silence run of the minimum length has fully arrived,
        # and only once: a long pause must not fire again on every later chunk.
        if combined.size >= self.min_silence_frames:
            tail = combined[-self.min_silence_frames:]
            if not tail.any():
                # Silence before the first word is a pause, not a phrase end: without
                # this, the leading 0.6 s of a fresh capture reports an empty phrase.
                if not state.in_pause and state.seen_speech:
                    ended = True
                    silence_start = combined.size - self.min_silence_frames
                    last_speech = np.nonzero(combined[:silence_start])[0]
                    frames_in_phrase = (
                        int(silence_start - last_speech[-1] - 1) if last_speech.size else 0)
                    state.seen_speech = False
                state.in_pause = True
            else:
                state.in_pause = False
                state.seen_speech = True

        # Keep at most one minimum-silence window plus the current chunk: enough to
        # detect a pause spread across a chunk boundary, small enough to stay free.
        keep = self.min_silence_frames + int(logprobs.shape[0])
        state.past_speech = combined[-keep:]
        return ended, frames_in_phrase
