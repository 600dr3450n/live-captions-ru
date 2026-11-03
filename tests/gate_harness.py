#!/usr/bin/env python3
"""Offline T-one run over files: text, RMS, time.

Serves as the baseline for comparing before/after the energy cutoff.
"""
from __future__ import annotations

import os
import sys
import time
import wave
from pathlib import Path

import numpy as np

ROOT = Path(os.environ.get("LCRU_ROOT") or Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(ROOT / "app"))

from asr import SAMPLE_RATE, Stream, TOneStreamingASR  # noqa: E402

MODEL_DIR = Path(os.environ.get("LCRU_MODEL_DIR") or ROOT / "models" / "t-one")


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as handle:
        assert handle.getnchannels() == 1 and handle.getframerate() == SAMPLE_RATE
        raw = handle.readframes(handle.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def transcribe(asr: TOneStreamingASR, samples: np.ndarray, block: int = 4800) -> tuple[str, float]:
    stream = asr.create_stream()
    started = time.perf_counter()
    for offset in range(0, samples.size, block):
        asr.feed(stream, samples[offset:offset + block], SAMPLE_RATE)
    text = asr.feed(stream, np.zeros(0, dtype=np.float32), SAMPLE_RATE) if False else stream.text
    elapsed = time.perf_counter() - started
    return text.strip(), elapsed


def main() -> int:
    paths = [Path(arg) for arg in sys.argv[1:]]
    if not paths:
        print("укажи wav-файлы")
        return 2
    asr = TOneStreamingASR(MODEL_DIR, num_threads=4)
    for path in paths:
        samples = read_wav(path)
        rms = float(np.sqrt(np.mean(samples**2)))
        peak = float(np.abs(samples).max())
        text, elapsed = transcribe(asr, samples)
        print(f"\n=== {path.name} ===")
        print(f"длительность {samples.size / SAMPLE_RATE:.1f} с, RMS {rms:.4f}, пик {peak:.3f}, "
              f"прогон {elapsed:.1f} с ({samples.size / SAMPLE_RATE / elapsed:.1f}x реального времени)")
        print(f"текст ({len(text)} симв.): {text[:600]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
