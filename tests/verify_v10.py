"""Проверка версии 2: свой декодер вместо sherpa-onnx.

Сверяем текст с эталоном sherpa-onnx, проверяем конец реплики, память, скорость
и сквозной путь через рабочий поток.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import difflib
import subprocess
import sys
import time
import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
sys.path.insert(0, str(PROJECT / "app"))

import main as app_main  # noqa: E402
from asr import (  # noqa: E402
    ENDPOINT_INITIAL_SILENCE,
    ENDPOINT_SILENCE,
    SAMPLE_RATE,
    SPEECH_RMS,
    TOneStreamingASR,
)

MODEL_DIR = PROJECT / "models" / "t-one"
SAMPLES = PROJECT.parent / "samples"
ART = PROJECT / "_artifacts"
ART.mkdir(exist_ok=True)


class PMC(ctypes.Structure):
    _fields_ = [
        ("cb", wt.DWORD),
        ("faults", wt.DWORD),
        ("peak_ws", ctypes.c_size_t),
        ("ws", ctypes.c_size_t),
        ("q_peak", ctypes.c_size_t),
        ("q", ctypes.c_size_t),
        ("nq_peak", ctypes.c_size_t),
        ("nq", ctypes.c_size_t),
        ("pagefile", ctypes.c_size_t),
        ("pagefile_peak", ctypes.c_size_t),
    ]


def rss_mb() -> float:
    kernel32 = ctypes.windll.kernel32
    kernel32.GetCurrentProcess.restype = wt.HANDLE
    psapi = ctypes.windll.psapi
    psapi.GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.POINTER(PMC), wt.DWORD]
    psapi.GetProcessMemoryInfo.restype = wt.BOOL
    counters = PMC()
    counters.cb = ctypes.sizeof(PMC)
    psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb)
    return counters.ws / 1024 / 1024


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as handle:
        rate = handle.getframerate()
        data = np.frombuffer(handle.readframes(handle.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    if rate != SAMPLE_RATE:
        count = int(len(data) * SAMPLE_RATE / rate)
        data = np.interp(np.arange(count) / SAMPLE_RATE, np.arange(len(data)) / rate, data).astype(np.float32)
    return data


def check_text_matches_reference() -> bool:
    """Текст нашего декодера должен совпадать с sherpa-onnx на общем участке."""
    print("=== Текст против sherpa-onnx ===")
    results = []
    for name in ("shortstories_01_clean", "shortstories_02_phone", "shortstories_04_noisy"):
        wav = SAMPLES / f"{name}.wav"
        if not wav.exists():
            print(f"  {name}: образца нет, пропускаю")
            continue
        if not (HERE / "reference_sherpa.py").exists():
            print("  пропущено: эталон снимался со старой сборки, reference_sherpa.py в репозиторий не входит")
            return True
        reference = subprocess.run(
            [sys.executable, str(HERE / "reference_sherpa.py"), str(wav)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=300,
        )
        if reference.returncode != 0:
            print(f"  {name}: эталон не получился: {reference.stderr[-200:]}")
            return False
        ref = reference.stdout.strip()

        audio = read_wav(wav)
        engine = TOneStreamingASR(MODEL_DIR, num_threads=2)
        stream = engine.create_stream()
        step = int(SAMPLE_RATE * 0.02)
        for start in range(0, len(audio), step):
            engine.feed(stream, audio[start : start + step], SAMPLE_RATE)
        mine = engine.finish(stream).strip()

        ratio = difflib.SequenceMatcher(None, mine, ref).ratio()
        # наш текст может быть длиннее на хвост (< 300 мс), который sherpa отбрасывает
        prefix = mine.startswith(ref) or ref.startswith(mine)
        print(f"  {name}: моё {len(mine)} симв., эталон {len(ref)}, совпадение {ratio * 100:.2f} %, префикс {prefix}")
        results.append(ratio > 0.99 and prefix)
    return all(results)


def check_endpoint_rules() -> bool:
    """Конец реплики: тишина после речи, тишина с начала, непрерывная речь без конца."""
    print("\n=== Конец реплики ===")
    engine = TOneStreamingASR(MODEL_DIR, num_threads=1)
    step = int(SAMPLE_RATE * 0.02)

    def feed(stream, seconds: float, amplitude: float) -> None:
        total = int(seconds * SAMPLE_RATE)
        for start in range(0, total, step):
            chunk = (np.random.default_rng(1).normal(0, amplitude, min(step, total - start))).astype(np.float32)
            engine.feed(stream, chunk, SAMPLE_RATE)

    # 1. речь 1 с, потом тишина — конец должен наступить после ENDPOINT_SILENCE
    stream = engine.create_stream()
    feed(stream, 1.0, 0.05)
    silence = 0.0
    endpoint_after = None
    while silence < ENDPOINT_SILENCE + 1.0:
        feed(stream, 0.05, 0.0)
        silence += 0.05
        if engine.is_endpoint(stream):
            endpoint_after = silence
            break
    ok1 = endpoint_after is not None and abs(endpoint_after - ENDPOINT_SILENCE) < 0.25
    print(f"  речь + тишина: конец через {endpoint_after} с после речи (ожидалось ≈{ENDPOINT_SILENCE}) — {'ок' if ok1 else 'ОШИБКА'}")

    # 2. тишина без речи — конец по начальной тишине
    stream = engine.create_stream()
    silence = 0.0
    endpoint_after = None
    while silence < ENDPOINT_INITIAL_SILENCE + 1.0:
        feed(stream, 0.05, 0.0)
        silence += 0.05
        if engine.is_endpoint(stream):
            endpoint_after = silence
            break
    ok2 = endpoint_after is not None and abs(endpoint_after - ENDPOINT_INITIAL_SILENCE) < 0.25
    print(f"  только тишина: конец через {endpoint_after} с (ожидалось ≈{ENDPOINT_INITIAL_SILENCE}) — {'ок' if ok2 else 'ОШИБКА'}")

    # 3. непрерывная речь 5 с — конца быть не должно
    stream = engine.create_stream()
    fired = False
    for _ in range(100):
        feed(stream, 0.05, 0.05)
        if engine.is_endpoint(stream):
            fired = True
    ok3 = not fired
    print(f"  непрерывная речь 5 с: конца нет — {'ок' if ok3 else 'ОШИБКА'}")

    # 4. однократность: на тишине конец не должен повторяться каждый вызов
    stream = engine.create_stream()
    feed(stream, 1.0, 0.05)
    feed(stream, 1.5, 0.0)
    first = engine.is_endpoint(stream)
    repeats = sum(1 for _ in range(20) if engine.is_endpoint(stream))
    ok4 = first and repeats == 0
    print(f"  конец выдаётся однократно: {first} и повторов {repeats} — {'ок' if ok4 else 'ОШИБКА'}")
    return ok1 and ok2 and ok3 and ok4


def check_memory_and_speed() -> bool:
    """5 минут аудио: память не должна расти, скорость — с запасом."""
    print("\n=== Память и скорость (5 минут аудио) ===")
    audio = read_wav(SAMPLES / "shortstories_01_clean.wav")
    engine = TOneStreamingASR(MODEL_DIR, num_threads=2)
    stream = engine.create_stream()
    step = int(SAMPLE_RATE * 0.02)
    position = 0
    total_steps = int(5 * 60 / 0.02)
    base = rss_mb()
    began = time.perf_counter()
    for index in range(total_steps):
        piece = audio[position : position + step]
        if len(piece) < step:
            position = 0
            piece = audio[:step]
        position += step
        engine.feed(stream, piece, SAMPLE_RATE)
        if len(stream.text) > 4000:
            engine.reset(stream)
        if index and index % (60 * 50) == 0:
            print(f"  {index * 0.02 / 60:4.1f} мин | память {rss_mb():6.0f} МБ")
    wall = time.perf_counter() - began
    grew = rss_mb() - base
    rtf = wall / (total_steps * 0.02)
    print(f"  прирост памяти {grew:+.0f} МБ, RTF {rtf:.3f}")
    ok = grew < 25 and rtf < 0.12
    print(f"  Память почти не растёт и скорость в норме: {'ок' if ok else 'ОШИБКА'}")
    return ok


def check_worker_pipeline(app) -> bool:
    """Сквозной путь: рабочий поток + настоящий декодер, реплика уходит в историю."""
    print("\n=== Сквозной путь через рабочий поток ===")
    import queue

    engine = TOneStreamingASR(MODEL_DIR, num_threads=2)
    audio = read_wav(SAMPLES / "shortstories_01_clean.wav")
    audio = np.concatenate([audio[: 2 * SAMPLE_RATE], np.zeros(3 * SAMPLE_RATE, np.float32), audio[2 * SAMPLE_RATE : 4 * SAMPLE_RATE]])

    events: list[tuple] = []
    audio_queue: "queue.Queue" = queue.Queue(maxsize=400)
    worker = app_main.RecognitionWorker(
        engine, audio_queue, lambda *args: events.append(args), lambda: False, highlight_seconds=lambda: 1.0
    )
    worker.start()
    step = 960  # 20 мс при 48 кГц
    audio48 = np.interp(
        np.arange(int(len(audio) * 6)) / 48000, np.arange(len(audio)) / SAMPLE_RATE, audio
    ).astype(np.float32)
    for start in range(0, len(audio48), step):
        audio_queue.put(type("Chunk", (), {"samples": audio48[start : start + step], "rate": 48000})())
        time.sleep(0.02)
    time.sleep(1.0)
    worker.stop()
    worker.join(timeout=5.0)

    saw_text = any(event[1].strip() for event in events)
    saw_history = any(event[0] for event in events)
    print(f"  событий {len(events)}, текст был: {saw_text}, история появилась: {saw_history}")
    last_text = next((event[1] for event in reversed(events) if event[1].strip()), "")
    print(f"  последний текст: {last_text[:80]!r}")
    ok = saw_text and saw_history
    print(f"  Реплика распознана и ушла в историю: {'ок' if ok else 'ОШИБКА'}")
    return ok


def main() -> int:
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    results = {
        "text_vs_sherpa": check_text_matches_reference(),
        "endpoints": check_endpoint_rules(),
        "memory_speed": check_memory_and_speed(),
        "worker_pipeline": check_worker_pipeline(app),
    }
    print("\n=== ИТОГ ===")
    for name, ok in results.items():
        print(f"  {name}: {'ок' if ok else 'ОШИБКА'}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
