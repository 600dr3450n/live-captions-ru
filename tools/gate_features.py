#!/usr/bin/env python3
"""Diagnostics: is there a feature separating speech from noise/hum/tone other than loudness.

Computed per 300 ms chunk (as in the model) over 20 ms frame statistics:
  cv  — coefficient of variation of frame energy (speech is syllable-modulated)
  p2r — peak factor of the chunk

This is not a test but a measuring tool: it prints a table and asserts nothing,
so it lives in tools/, not tests/. The file set comes from LCRU_GATE_SET
(default: gate_set under the system temp dir), as in tests/gate_eval.py.
"""
from __future__ import annotations

import os
import tempfile
import wave
from pathlib import Path

import numpy as np

SET_DIR = Path(os.environ.get("LCRU_GATE_SET", Path(tempfile.gettempdir()) / "gate_set"))
CHUNK = 2400
FRAME = 160  # 20 ms at 8 kHz

FILES = [
    "speech_clean.wav",
    "speech_minus_20db.wav",
    "speech_minus_28db.wav",
    "speech_minus_34db.wav",
    "speech_minus_40db.wav",
    "speech_snr_8db.wav",
    "speech_snr_3db.wav",
    "speech_fast_1_5x.wav",
    "speech_fast_2x.wav",
    "speech_quiet_snr_10db.wav",
    "silence_30s.wav",
    "noise_floor_50db.wav",
    "hum_50hz.wav",
    "hiss_residual.wav",
    "tone_8k.wav",
    "noise_8k.wav",
]


def read(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as handle:
        raw = handle.readframes(handle.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def chunk_stats(chunk: np.ndarray) -> tuple[float, float, float]:
    usable = chunk.size - chunk.size % FRAME
    frames = chunk[:usable].reshape(-1, FRAME)
    energies = np.sqrt((frames**2).mean(axis=1))
    mean = float(energies.mean())
    cv = float(energies.std() / mean) if mean > 1e-9 else 0.0
    peak = float(np.abs(chunk).max())
    rms = float(np.sqrt(np.mean(chunk**2)))
    p2r = peak / rms if rms > 1e-9 else 0.0
    return rms, cv, p2r


print(f"{'файл':<26} {'RMS med':>8} {'cv med':>7} {'cv p90':>7} {'p2r med':>8} {'p2r p90':>8}  доля чанков cv<0.15")
for name in FILES:
    path = SET_DIR / name
    if not path.exists():
        print(f"{name:<26} НЕТ ФАЙЛА")
        continue
    samples = read(path)
    rows = [
        chunk_stats(samples[i:i + CHUNK])
        for i in range(0, samples.size - CHUNK + 1, CHUNK)
    ]
    if not rows:
        continue
    rms = np.array([r[0] for r in rows])
    cv = np.array([r[1] for r in rows])
    p2r = np.array([r[2] for r in rows])
    loud = rms > 1e-6
    share = float((cv[loud] < 0.15).mean() * 100) if loud.any() else 0.0
    print(f"{name:<26} {np.median(rms):8.4f} {np.median(cv):7.3f} {np.percentile(cv, 90):7.3f} "
          f"{np.median(p2r):8.2f} {np.percentile(p2r, 90):8.2f}  {share:5.1f}%")
