"""Phrase splitter on logits: synthetic data and the real model.

We check that the boundary is set by a pause of at least 0.6 s, that a short pause does not
tear a phrase, that a pause smeared across a chunk seam is still visible, and that on real
audio with a pause the engine reports the end of a phrase.
"""
from __future__ import annotations

import os
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

import asr as asr_mod  # noqa: E402
from phrase_splitter import PhraseSplitter, SplitterState  # noqa: E402

MODEL_DIR = Path(os.environ.get("LCRU_MODEL_DIR") or ROOT / "models" / "t-one")
SAMPLES = Path(
    os.environ.get("LCRU_GATE_SET") or Path(tempfile.gettempdir()) / "gate_set"
) / "speech_clean.wav"
failures: list[str] = []


def check(condition: bool, label: str) -> None:
    if condition:
        print(f"  ok   {label}")
    else:
        failures.append(label)
        print(f"  FAIL {label}")


def speech_frames(count: int) -> np.ndarray:
    """Speech frames: space+blank are near zero, so the speech probability is high."""
    frame = np.full(35, -0.04, dtype=np.float32)
    frame[33] = -8.0
    frame[34] = -8.0
    return np.tile(frame, (count, 1))


def silence_frames(count: int) -> np.ndarray:
    return np.tile(PhraseSplitter.silence_frame(), (count, 1))


splitter = PhraseSplitter()

MIN_SILENCE = splitter.min_silence_frames
SHORT_SILENCE = MIN_SILENCE // 3

print(f"1. Пауза {MIN_SILENCE / 33.3:.1f} с ({MIN_SILENCE} кадров) закрывает фразу")
state = SplitterState()
ended = False
for block in (speech_frames(30), silence_frames(MIN_SILENCE)):
    hit, frames = splitter.push(state, block)
    ended = ended or hit
check(ended, f"фраза закрыта после {MIN_SILENCE} кадров тишины")

print(f"2. Пауза {SHORT_SILENCE / 33.3:.1f} с ({SHORT_SILENCE} кадров) фразу не рвёт")
state = SplitterState()
splitter.push(state, speech_frames(30))
hit, _ = splitter.push(state, silence_frames(SHORT_SILENCE))
check(not hit, "короткая пауза не закрывает фразу")

print("3. Пауза, размазанная по стыку чанков, видна")
state = SplitterState()
splitter.push(state, speech_frames(30))
first, _ = splitter.push(state, silence_frames(MIN_SILENCE - 8))
second, _ = splitter.push(state, silence_frames(8))
check(not first and second,
      f"{MIN_SILENCE - 8} кадров тишины + 8 кадров тишины = граница")

print("4. Непрерывная речь границу не даёт")
state = SplitterState()
hits = sum(splitter.push(state, speech_frames(10))[0] for _ in range(60))
check(hits == 0, "6 секунд речи без пауз — ни одной границы")

print("5. Реальная модель: пауза в аудио закрывает фразу")
engine = asr_mod.TOneStreamingASR(MODEL_DIR, num_threads=6)
with wave.open(str(SAMPLES), "rb") as handle:
    raw = handle.readframes(handle.getnframes())
speech = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
speech = speech[: asr_mod.SAMPLE_RATE * 4]
padded = np.concatenate([speech, np.zeros(asr_mod.SAMPLE_RATE * 2, dtype=np.float32)])
stream = engine.create_stream()
phrases_seen = 0
for offset in range(0, padded.size, 2400):
    engine.feed(stream, padded[offset:offset + 2400], asr_mod.SAMPLE_RATE)
    if getattr(stream, "phrase_ended", False):
        stream.phrase_ended = False
        phrases_seen += 1
check(phrases_seen >= 1, f"на речи с паузой сплиттер дал границу ({phrases_seen})")

print("6. Реальная модель: речь без пауз границ не даёт")
# The recording has real pauses (quiet chunks at 0.0-0.6 s and 2.4 s), so we take
# only chunks containing speech and concatenate them: such a signal has no pauses.
chunks = []
for offset in range(0, speech.size, 2400):
    piece = speech[offset:offset + 2400]
    if piece.size == 2400 and float(np.sqrt((piece ** 2).mean())) >= 0.02:
        chunks.append(piece)
speech_nogaps = np.concatenate(chunks) if chunks else speech
stream = engine.create_stream()
phrases_seen = 0
for offset in range(0, speech_nogaps.size, 2400):
    engine.feed(stream, speech_nogaps[offset:offset + 2400], asr_mod.SAMPLE_RATE)
    if getattr(stream, "phrase_ended", False):
        stream.phrase_ended = False
        phrases_seen += 1
check(phrases_seen == 0,
      f"{speech_nogaps.size / asr_mod.SAMPLE_RATE:.1f} с речи без пауз — границ нет ({phrases_seen})")
check(len(stream.text.strip()) > 20, f"текст при этом распознан ({len(stream.text)} символов)")

print("7. Гейт: отсечённые чанки тишины тоже считаются паузой")
stream = engine.create_stream()
silence = np.zeros(asr_mod.SAMPLE_RATE * 2, dtype=np.float32)
engine.feed(stream, np.concatenate([speech, silence]), asr_mod.SAMPLE_RATE)
check(stream.gated_chunks > 0, f"тишина отсечена гейтом ({stream.gated_chunks} чанков)")
check(stream.phrases >= 1, f"сплиттер увидел паузу через гейт ({stream.phrases} фраз)")

print()
if failures:
    print(f"ПРОВАЛЕНО {len(failures)}:")
    for item in failures:
        print("  -", item)
    sys.exit(1)
print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
