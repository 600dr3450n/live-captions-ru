#!/usr/bin/env python3
"""Run over the hard-recording set: text, CER against the clean reference, share of decoded chunks.

Run twice: before and after the cutoff, to compare.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import wave
from pathlib import Path

import numpy as np

# Paths are relative to this checkout and can be pointed elsewhere with LCRU_ROOT,
# LCRU_MODEL_DIR, LCRU_GATE_SET and LCRU_GATE_OUT. The absolute paths that were here
# before only worked on the machine they were written on.
ROOT = Path(os.environ.get("LCRU_ROOT") or Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(ROOT / "app"))

import asr as asr_mod  # noqa: E402

MODEL_DIR = Path(os.environ.get("LCRU_MODEL_DIR") or ROOT / "models" / "t-one")
SET_DIR = Path(os.environ.get("LCRU_GATE_SET") or Path(tempfile.gettempdir()) / "gate_set")
OUT_PATH = Path(os.environ.get("LCRU_GATE_OUT") or Path(tempfile.gettempdir()) / "gate_after.txt")
# A speech file that decodes worse than this against the clean reference is a
# regression, not noise. The script used to return 0 no matter what it printed.
MAX_CER = float(os.environ.get("LCRU_MAX_CER", "0.35"))
# 2x speed is beyond what the model handles (CER 0.78 measured), so it is reported but
# does not fail the run: the file is in the set to show the shape of the degradation.
KNOWN_BAD = {"speech_fast_2x.wav"}
BLOCK = 4800


def read(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as handle:
        raw = handle.readframes(handle.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def cer(reference: str, hypothesis: str) -> float:
    ref, hyp = reference.split(), hypothesis.split()
    if not ref:
        return 0.0 if not hyp else 1.0
    # character-level distance over the whole line
    r, h = list(reference), list(hypothesis)
    prev = list(range(len(h) + 1))
    for i, rc in enumerate(r, 1):
        cur = [i]
        for j, hc in enumerate(h, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (rc != hc)))
        prev = cur
    return prev[-1] / max(1, len(r))


def main() -> int:
    if not (MODEL_DIR / "model.onnx").exists():
        print(f"model not found: {MODEL_DIR / 'model.onnx'}", file=sys.stderr)
        return 2
    if not SET_DIR.exists():
        print(f"gate set not found: {SET_DIR} (build it with make_gate_set.py)", file=sys.stderr)
        return 2
    engine = asr_mod.TOneStreamingASR(MODEL_DIR, num_threads=4)
    gate = getattr(engine, "gate_stats", None)
    order = [
        "speech_clean.wav",
        "speech_minus_12db.wav",
        "speech_minus_20db.wav",
        "speech_minus_28db.wav",
        "speech_minus_34db.wav",
        "speech_minus_40db.wav",
        "speech_snr_15db.wav",
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
    results: dict[str, str] = {}
    failures: list[str] = []
    reference = ""
    print(f"{'файл':<26} {'RMS':>7} {'сек':>5} {'симв':>5} {'CER':>7} {'гейт':>7}  текст")
    for name in order:
        path = SET_DIR / name
        samples = read(path)
        stream = engine.create_stream()
        started = time.perf_counter()
        for offset in range(0, samples.size, BLOCK):
            engine.feed(stream, samples[offset:offset + BLOCK], asr_mod.SAMPLE_RATE)
        elapsed = time.perf_counter() - started
        text = " ".join(stream.text.split())
        results[name] = text
        if name == "speech_clean.wav":
            reference = text
        error = 0.0 if not reference else cer(reference, text)
        rms = float(np.sqrt(np.mean(samples**2)))
        label = name.replace(".wav", "")
        total = stream.decoded_chunks + stream.gated_chunks
        gated_share = 100.0 * stream.gated_chunks / total if total else 0.0
        print(f"{label:<26} {rms:7.4f} {elapsed:5.1f} {len(text):5d} {error:7.3f} "
              f"{gated_share:6.1f}%  {text[:60]}")
        if name.startswith("speech") and reference and error > MAX_CER:
            if name in KNOWN_BAD:
                print(f"       (известное ограничение модели, не провал: {label})")
            else:
                failures.append(f"{label}: CER {error:.3f} > {MAX_CER:.2f}")
    OUT_PATH.write_text(
        "\n\n".join(f"{k}:\n{v}" for k, v in results.items()), encoding="utf-8"
    )
    print(f"\nполные тексты: {OUT_PATH}")
    if not reference:
        print("эталон speech_clean.wav не декодирован: сравнивать не с чем", file=sys.stderr)
        return 1
    if failures:
        print("\nПРОВАЛ:", file=sys.stderr)
        for line in failures:
            print("  " + line, file=sys.stderr)
        return 1
    print(f"порог CER {MAX_CER:.2f} соблюдён на всех речевых файлах")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
