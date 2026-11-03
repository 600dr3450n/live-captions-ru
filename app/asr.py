"""Streaming Russian recognition with T-one and a custom CTC decoder."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import onnxruntime as ort

log = logging.getLogger(__name__)

SAMPLE_RATE = 8000
SAMPLES_PER_CHUNK = 2400
FRAMES_PER_CHUNK = 10
STATE_SIZE = 219729
BLANK_ID = 34
SPACE_ID = 33

from phrase_splitter import PhraseSplitter, SplitterState

ENDPOINT_SILENCE = 1.2
ENDPOINT_INITIAL_SILENCE = 2.4
ENDPOINT_MAX_UTTERANCE = 20.0
SPEECH_RMS = 0.008

# Energy gate. Loudness alone cannot separate speech from a stationary signal:
# the model still reads speech at RMS 0.0007, below the noise floor of a normal
# microphone, so a level threshold would silently eat quiet speech. What does
# separate them is modulation: over a 300 ms chunk speech swings between syllables
# (cv of 20 ms frame energy 0.31-0.84 in the test set), while hum, hiss, a tone or
# digital silence stay flat (cv 0.00-0.05). Chunks below the threshold are not sent
# to the model at all, which is where the idle CPU goes.
GATE_CV_THRESHOLD = 0.15
GATE_FRAME = 160            # 20 ms at 8 kHz
GATE_HOLD_CHUNKS = 4        # keep decoding 1.2 s after the last modulated chunk
GATE_PREROLL_CHUNKS = 2     # replay 0.6 s before the first modulated chunk
GATE_MIN_RMS = 1e-5         # true digital silence is never worth a model call
GATE_RESET_CHUNKS = 10      # after 3 s of gated silence, start the state clean


def load_tokens(path: Path) -> dict[int, str]:
    tokens: dict[int, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        symbol, _, index = line.rpartition(" ")
        tokens[int(index)] = symbol
    return tokens


_FIR_CACHE: dict[tuple[int, int], np.ndarray] = {}


def _anti_alias_kernel(src: int, dst: int, taps: int = 129) -> np.ndarray:
    """Windowed-sinc low-pass that keeps everything below 0.45*dst.

    129 taps put the transition band at about +-500 Hz around the cutoff: 33 taps
    attenuated 4-5 kHz by only 9-21 dB, so sibilants and hiss folded back into the
    speech band. The filter costs about 2 ms per 300 ms chunk.
    """
    key = (src, dst)
    cached = _FIR_CACHE.get(key)
    if cached is not None:
        return cached
    cutoff = 0.45 * dst / src
    positions = np.arange(taps) - (taps - 1) / 2.0
    kernel = np.sinc(2.0 * cutoff * positions) * np.hamming(taps)
    kernel = (kernel / kernel.sum()).astype(np.float32)
    _FIR_CACHE[key] = kernel
    return kernel


class Resampler:
    """Streaming anti-alias resampler: filter history and phase carry across blocks.

    Filtering every block on its own pretended the signal started from zero at each
    boundary, so both ends of every 300 ms chunk carried a step that is not in the real
    audio. Two things are carried instead: the input samples the filter still needs,
    and the fractional position of the next output sample. The output of a block is
    therefore delayed by half a kernel, which is 8 ms at 8 kHz and invisible to the
    model, and the trailing samples are flushed by the next block (the worker always
    pads 0.6 s of silence before dropping a stream).
    """

    def __init__(self, src: int, dst: int) -> None:
        self.src = src
        self.dst = dst
        self._kernel = _anti_alias_kernel(src, dst)
        self._taps = len(self._kernel)
        self._half = self._taps // 2
        self._step = src / dst  # input samples per output sample
        self._zeros = np.zeros(self._half, dtype=np.float32)
        self._tail = np.zeros(0, dtype=np.float32)
        self._pos = 0.0  # position of the next output sample inside the tail buffer

    def matches(self, src: int, dst: int) -> bool:
        return self.src == src and self.dst == dst

    def reset(self) -> None:
        self._tail = np.zeros(0, dtype=np.float32)
        self._pos = 0.0

    def process(self, samples: np.ndarray) -> np.ndarray:
        data = np.asarray(samples, dtype=np.float32)
        if data.size == 0:
            return data
        if self.src == self.dst:
            return data
        if self.src < self.dst:
            count = int(len(data) * self.dst / self.src)
            if count <= 0:
                return np.zeros(0, dtype=np.float32)
            return np.interp(np.arange(count) / self.dst, np.arange(len(data)) / self.src, data).astype(
                np.float32
            )
        buffer = np.concatenate([self._tail, data]) if self._tail.size else data
        # A centre needs _half samples on both sides; the ones on the right are not
        # available yet for the last samples of the block, so they wait for the next.
        usable = len(buffer) - 1 - self._half
        if usable <= 0 or self._pos > usable - 1:
            self._tail = buffer
            return np.zeros(0, dtype=np.float32)
        filtered = np.convolve(np.concatenate([self._zeros, buffer]), self._kernel, mode="valid")[:usable]
        count = int(np.floor((usable - 1 - self._pos) / self._step)) + 1
        positions = self._pos + np.arange(count, dtype=np.float64) * self._step
        out = np.interp(positions, np.arange(usable), filtered).astype(np.float32)
        next_pos = self._pos + count * self._step
        # Keep the samples the filter needs for the next centre, and always make
        # progress so the buffer cannot grow without bound.
        advance = int(min(usable, max(1, np.floor(next_pos) - self._half)))
        self._tail = buffer[advance:]
        self._pos = next_pos - advance
        return out


def resample(samples: np.ndarray, src: int, dst: int) -> np.ndarray:
    """One-shot resample for callers that have no stream state (tests, probes)."""
    return Resampler(src, dst).process(samples)


@dataclass
class Stream:

    state: np.ndarray
    buffer: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.float32))
    text: str = ""
    prev_id: int = -1
    samples_seen: int = 0
    speech_started_at: int = -1
    last_speech_at: int = 0
    resampler: "Resampler | None" = None
    endpoint_latched: bool = False
    gate_hold_left: int = 0
    gate_skipped_run: int = 0
    gate_preroll: list = field(default_factory=list)
    gated_chunks: int = 0
    decoded_chunks: int = 0
    splitter: SplitterState = field(default_factory=SplitterState)
    phrase_ended: bool = False  # set by the splitter, cleared by the worker
    phrases: int = 0
    phrase_frames: int = 0


class TOneStreamingASR:

    def __init__(self, model_dir: Path, num_threads: int = 4) -> None:
        started = time.perf_counter()
        self._tokens = load_tokens(model_dir / "tokens.txt")
        options = ort.SessionOptions()
        options.intra_op_num_threads = num_threads
        options.inter_op_num_threads = 1
        options.enable_cpu_mem_arena = False
        options.enable_mem_pattern = False
        self._splitter = PhraseSplitter()
        self._session = ort.InferenceSession(
            str(model_dir / "model.onnx"), sess_options=options, providers=["CPUExecutionProvider"]
        )
        log.info(
            "model_loaded model=t-one-own-decoder threads=%d load_time_s=%.2f",
            num_threads,
            time.perf_counter() - started,
        )

    # ------------------------------------------------------------- streams
    def _state_type(self):
        """dtype of the recurrent state, as expected by the loaded model."""
        return np.float16 if "float16" in self._session.get_inputs()[1].type else np.float32

    def create_stream(self) -> Stream:
        return Stream(state=np.zeros((1, STATE_SIZE), dtype=self._state_type()))

    def reset(self, stream: Stream) -> None:
        stream.state = np.zeros((1, STATE_SIZE), dtype=self._state_type())
        stream.buffer = np.zeros(0, dtype=np.float32)
        stream.text = ""
        stream.prev_id = -1
        stream.samples_seen = 0
        stream.speech_started_at = -1
        stream.last_speech_at = 0
        stream.resampler = None
        stream.endpoint_latched = False
        stream.gate_hold_left = 0
        stream.gate_skipped_run = 0
        stream.gate_preroll = []
        stream.gated_chunks = 0
        stream.decoded_chunks = 0
        stream.splitter = SplitterState()
        stream.phrase_ended = False
        stream.phrases = 0
        stream.phrase_frames = 0

    # -------------------------------------------------------------- feeding
    def feed(self, stream: Stream, samples: np.ndarray, sample_rate: int) -> str:
        resampler = stream.resampler
        if resampler is None or not resampler.matches(sample_rate, SAMPLE_RATE):
            resampler = Resampler(sample_rate, SAMPLE_RATE)
            stream.resampler = resampler
        pcm = resampler.process(np.asarray(samples, dtype=np.float32))
        if pcm.size:
            self._track_energy(stream, pcm)
            stream.buffer = np.concatenate([stream.buffer, pcm]) if stream.buffer.size else pcm.copy()
        while stream.buffer.size >= SAMPLES_PER_CHUNK:
            chunk = stream.buffer[:SAMPLES_PER_CHUNK]
            stream.buffer = stream.buffer[SAMPLES_PER_CHUNK:]
            self._feed_chunk(stream, chunk)
        return stream.text

    def _modulation(self, chunk: np.ndarray) -> float:
        """cv of 20 ms frame energy: high for speech, near zero for a steady signal."""
        usable = chunk.size - chunk.size % GATE_FRAME
        if usable <= 0:
            return 0.0
        frames = chunk[:usable].reshape(-1, GATE_FRAME)
        energies = np.sqrt((frames.astype(np.float32) ** 2).mean(axis=1))
        mean = float(energies.mean())
        if mean <= GATE_MIN_RMS:
            return 0.0
        return float(energies.std() / mean)

    def _feed_chunk(self, stream: Stream, chunk: np.ndarray) -> None:
        """Decode a chunk only when it can carry speech; replay the run-up when it can."""
        rms = float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))
        speechy = rms > GATE_MIN_RMS and self._modulation(chunk) >= GATE_CV_THRESHOLD
        if speechy:
            if stream.gate_skipped_run > GATE_RESET_CHUNKS:
                # Long silence behind us: start from a clean recurrent state so the
                # first word after the pause cannot glue itself to the last one.
                stream.state = np.zeros((1, STATE_SIZE), dtype=self._state_type())
                stream.prev_id = -1
            for buffered in stream.gate_preroll:
                self._run(stream, buffered)
                stream.decoded_chunks += 1
            stream.gate_preroll.clear()
            stream.gate_skipped_run = 0
            stream.gate_hold_left = GATE_HOLD_CHUNKS
            self._run(stream, chunk)
            stream.decoded_chunks += 1
            return
        if stream.gate_hold_left > 0:
            stream.gate_hold_left -= 1
            stream.gate_skipped_run = 0
            self._run(stream, chunk)
            stream.decoded_chunks += 1
            return
        stream.gate_skipped_run += 1
        stream.gated_chunks += 1
        # The model never sees this chunk, but the splitter must: a real pause has to
        # close the phrase even when the gate already swallowed the quiet part.
        self._push_splitter(stream, PhraseSplitter.silence_frame().repeat(
            FRAMES_PER_CHUNK, axis=0))
        stream.gate_preroll.append(chunk.copy())
        del stream.gate_preroll[:-GATE_PREROLL_CHUNKS]

    def push(self, stream: Stream, samples: np.ndarray, sample_rate: int) -> None:
        self.feed(stream, samples, sample_rate)

    def text(self, stream: Stream) -> str:
        return stream.text

    def finish(self, stream: Stream) -> str:
        if stream.buffer.size:
            real = stream.buffer.size
            frames = min(
                FRAMES_PER_CHUNK,
                max(1, int(np.ceil(real / (SAMPLES_PER_CHUNK / FRAMES_PER_CHUNK)))),
            )
            padded = np.zeros(SAMPLES_PER_CHUNK, dtype=np.float32)
            padded[:real] = stream.buffer
            stream.buffer = np.zeros(0, dtype=np.float32)
            self._run(stream, padded, frames=frames)
        return stream.text

    def timestamps(self, stream: Stream) -> list[float]:
        return []

    # ---------------------------------------------------------------- inner
    def _run(self, stream: Stream, chunk: np.ndarray, frames: int | None = None) -> None:
        signal = np.clip(chunk * 32767.0, -32768, 32767).astype(np.int32).reshape(1, -1, 1)
        logprobs, stream.state = self._session.run(None, {"signal": signal, "state": stream.state})
        block = logprobs[0] if frames is None else logprobs[0, :frames]
        self._push_splitter(stream, block)
        ids = block.argmax(axis=-1)
        for token in ids:
            index = int(token)
            if index == stream.prev_id:
                continue
            stream.prev_id = index
            if index == BLANK_ID:
                continue
            stream.text += " " if index == SPACE_ID else self._tokens.get(index, "")

    def _push_splitter(self, stream: Stream, logprobs: np.ndarray) -> None:
        """Ask the model's own log-probabilities where the phrase ends."""
        try:
            ended, frames = self._splitter.push(stream.splitter, logprobs)
        except Exception as exc:  # noqa: BLE001
            log.warning("splitter_failed error=%r action=ignore", exc)
            return
        if ended:
            stream.phrase_ended = True
            stream.phrases += 1
            stream.phrase_frames = frames

    def _track_energy(self, stream: Stream, pcm: np.ndarray) -> None:
        rms = float(np.sqrt(np.mean(pcm**2))) if pcm.size else 0.0
        stream.samples_seen += pcm.size
        if rms >= SPEECH_RMS:
            if stream.speech_started_at < 0:
                stream.speech_started_at = stream.samples_seen
            stream.last_speech_at = stream.samples_seen

    def is_endpoint(self, stream: Stream) -> bool:
        now = stream.samples_seen / SAMPLE_RATE
        silence = now - stream.last_speech_at / SAMPLE_RATE
        if stream.speech_started_at < 0:
            done = now > ENDPOINT_INITIAL_SILENCE
        else:
            utterance = (stream.samples_seen - stream.speech_started_at) / SAMPLE_RATE
            done = silence > ENDPOINT_SILENCE or utterance > ENDPOINT_MAX_UTTERANCE
        if done and not stream.endpoint_latched:
            stream.endpoint_latched = True
            return True
        if not done and stream.endpoint_latched:
            stream.endpoint_latched = False
        return False

    def to_mono(self, block: np.ndarray) -> np.ndarray:
        if block.ndim == 2 and block.shape[1] > 1:
            return block.mean(axis=1, dtype=np.float32)
        return np.asarray(block, dtype=np.float32).reshape(-1)
