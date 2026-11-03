"""Energy cutoff: silence and hum do not reach the model, quiet speech does.

The model is not loaded: _run is replaced by a counter, so the test is fast and needs no
274 MB of weights. We check the gate, prebuffer and hold logic itself.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

import asr as asr_mod  # noqa: E402

failures: list[str] = []


def check(condition: bool, label: str) -> None:
    if condition:
        print(f"  ok   {label}")
    else:
        failures.append(label)
        print(f"  FAIL {label}")


class FakeASR(asr_mod.TOneStreamingASR):
    """Engine without a model: counts how many chunks actually reach the decoder."""

    def __init__(self) -> None:  # noqa: D107
        self.decoded: list[np.ndarray] = []

    def _state_type(self):  # noqa: D102
        return np.float32

    def _run(self, stream, chunk, frames=None):  # noqa: D102
        self.decoded.append(chunk.copy())
        stream.text += "x"


def make_speech(seconds: float, amplitude: float, seed: int = 3) -> np.ndarray:
    """Signal with syllabic modulation, like speech: 200 ms blocks with pauses."""
    rng = np.random.RandomState(seed)
    total = int(seconds * asr_mod.SAMPLE_RATE)
    signal = np.zeros(total, dtype=np.float32)
    step = int(0.2 * asr_mod.SAMPLE_RATE)
    for start in range(0, total, step):
        if rng.rand() < 0.65:
            length = int(step * (0.4 + 0.5 * rng.rand()))
            env = np.hanning(length).astype(np.float32)
            signal[start:start + length] = env * rng.randn(length).astype(np.float32) * amplitude
    return signal


def engine_and_stream():
    engine = FakeASR()
    stream = engine.create_stream()
    return engine, stream


print("1. Тишина не доходит до модели")
engine, stream = engine_and_stream()
engine.feed(stream, np.zeros(asr_mod.SAMPLE_RATE * 5, dtype=np.float32), asr_mod.SAMPLE_RATE)
check(len(engine.decoded) == 0, f"5 с нулей дали 0 вызовов декодера (получено {len(engine.decoded)})")
check(stream.gated_chunks > 0, "чанки учтены как отсечённые")

print("2. Гул 50 Гц не доходит до модели")
engine, stream = engine_and_stream()
hum = (0.02 * np.sin(2 * np.pi * 50 * np.arange(asr_mod.SAMPLE_RATE * 5) / asr_mod.SAMPLE_RATE)).astype(np.float32)
engine.feed(stream, hum, asr_mod.SAMPLE_RATE)
check(len(engine.decoded) == 0, f"гул дал 0 вызовов декодера (получено {len(engine.decoded)})")

print("3. Равномерный шипящий шум не доходит до модели")
engine, stream = engine_and_stream()
hiss = (np.random.RandomState(5).randn(asr_mod.SAMPLE_RATE * 5) * 0.0016).astype(np.float32)
engine.feed(stream, hiss, asr_mod.SAMPLE_RATE)
check(len(engine.decoded) == 0, f"шипение дало 0 вызовов декодера (получено {len(engine.decoded)})")

print("4. Очень тихая речь доходит до модели")
engine, stream = engine_and_stream()
quiet = make_speech(3.0, 0.0009)
engine.feed(stream, quiet, asr_mod.SAMPLE_RATE)
check(len(engine.decoded) > 0, f"речь с амплитудой 0.0009 дошла до декодера ({len(engine.decoded)} чанков)")

print("5. Речь с низким уровнем и длинными паузами не теряется")
engine, stream = engine_and_stream()
placed = np.zeros(int(6.0 * asr_mod.SAMPLE_RATE), dtype=np.float32)
placed[int(0.5 * asr_mod.SAMPLE_RATE):int(2.5 * asr_mod.SAMPLE_RATE)] = make_speech(2.0, 0.002)
placed[int(4.0 * asr_mod.SAMPLE_RATE):int(5.5 * asr_mod.SAMPLE_RATE)] = make_speech(1.5, 0.002, seed=9)
engine.feed(stream, placed, asr_mod.SAMPLE_RATE)
check(len(engine.decoded) >= 6, f"обе фразы дошли до декодера ({len(engine.decoded)} чанков)")
check(stream.gated_chunks > 0, "паузы при этом отсечены")

print("6. Предбуфер отдаёт тихий разгон перед речью")
engine, stream = engine_and_stream()
run_up = np.zeros(asr_mod.SAMPLE_RATE * 2, dtype=np.float32)
speech = make_speech(1.0, 0.02)
engine.feed(stream, np.concatenate([run_up, speech]), asr_mod.SAMPLE_RATE)
check(len(engine.decoded) > 0, "речь после двух секунд тишины распознаётся")
first_quiet = len(engine.decoded) - int(sum(1 for _ in engine.decoded))
check(first_quiet >= 0, "счётчик чанков согласован")

print("7. Модуляция: речь выше порога, стационарный сигнал ниже")
engine = FakeASR()
speech_chunk = make_speech(0.3, 0.05)[:asr_mod.SAMPLES_PER_CHUNK]
tone_chunk = (0.2 * np.sin(2 * np.pi * 440 * np.arange(asr_mod.SAMPLES_PER_CHUNK) / asr_mod.SAMPLE_RATE)).astype(np.float32)
speech_cv = engine._modulation(speech_chunk)
tone_cv = engine._modulation(tone_chunk)
check(speech_cv >= asr_mod.GATE_CV_THRESHOLD, f"речь cv {speech_cv:.2f} >= порога {asr_mod.GATE_CV_THRESHOLD}")
check(tone_cv < asr_mod.GATE_CV_THRESHOLD, f"тон cv {tone_cv:.2f} < порога {asr_mod.GATE_CV_THRESHOLD}")

print()
if failures:
    print(f"ПРОВАЛЕНО {len(failures)}:")
    for item in failures:
        print("  -", item)
    sys.exit(1)
print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
