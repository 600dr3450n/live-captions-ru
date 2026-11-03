#!/usr/bin/env python3
"""Готовит набор сложных записей: тихие, шумные, быстрые, тишина, гул, шум."""
from __future__ import annotations

import os
import tempfile
import wave
from pathlib import Path

import numpy as np

# Overridable, because the absolute paths that used to be here only existed on one
# machine: LCRU_GATE_SRC points at a clean 8 kHz mono recording, LCRU_GATE_SET at the
# output directory.
SRC = Path(os.environ.get("LCRU_GATE_SRC") or "test_ru2.wav")
OUT = Path(os.environ.get("LCRU_GATE_SET") or Path(tempfile.gettempdir()) / "gate_set")
RATE = 8000


def read(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as handle:
        raw = handle.readframes(handle.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def write(name: str, samples: np.ndarray) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    data = np.clip(samples, -1.0, 1.0)
    pcm = (data * 32767).astype(np.int16)
    with wave.open(str(OUT / name), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(pcm.tobytes())
    rms = float(np.sqrt(np.mean(data**2)))
    print(f"  {name:<26} RMS {rms:.5f}")


def rms_of(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x**2)))


def speech_like_noise(n: int, rng: np.random.RandomState) -> np.ndarray:
    """Шум с речевой огибающей: похож на гулкий офис, а не на белый шум."""
    env = 0.25 + 0.75 * np.abs(np.sin(2 * np.pi * 0.7 * np.arange(n) / RATE + 0.4))
    return rng.randn(n).astype(np.float32) * env


def fast(samples: np.ndarray, factor: float) -> np.ndarray:
    """Ускорение темпа через простую передискретизацию: речь становится неразборчивой."""
    count = int(len(samples) / factor)
    return np.interp(np.arange(count) * factor, np.arange(len(samples)), samples).astype(np.float32)


def main() -> int:
    speech = read(SRC)
    n = speech.size
    rng = np.random.RandomState(11)
    print(f"исходник: {n / RATE:.1f} с, RMS {rms_of(speech):.4f}")

    write("speech_clean.wav", speech)
    for db in (12, 20, 28, 34, 40):
        write(f"speech_minus_{db}db.wav", speech * 10 ** (-db / 20))

    base = rms_of(speech)
    for snr in (15, 8, 3):
        noise = speech_like_noise(n, rng)
        noise *= base / rms_of(noise) / 10 ** (snr / 20)
        write(f"speech_snr_{snr}db.wav", speech + noise)

    write("speech_fast_1_5x.wav", fast(speech, 1.5))
    write("speech_fast_2x.wav", fast(speech, 2.0))

    # очень тихая речь в шумной комнате: оба фактора сразу
    noise = speech_like_noise(n, rng)
    quiet = speech * 10 ** (-20 / 20)
    noise *= rms_of(quiet) / rms_of(noise) / 10 ** (10 / 20)
    write("speech_quiet_snr_10db.wav", quiet + noise)

    # не должно давать текста
    write("silence_30s.wav", np.zeros(30 * RATE, dtype=np.float32))
    write("noise_floor_50db.wav", rng.randn(30 * RATE).astype(np.float32) * 10 ** (-50 / 20))
    hum = 0.02 * np.sin(2 * np.pi * 50 * np.arange(30 * RATE) / RATE)
    write("hum_50hz.wav", hum.astype(np.float32))
    write("hiss_residual.wav", (rng.randn(20 * RATE).astype(np.float32) * 0.0016))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
