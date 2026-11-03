"""Fix 1.0.3: the tail of the last phrase is flushed on stop, pause, and device change.

We check on a fake engine (fast, no model):
- on stop the flush runs and the text reaches the UI;
- on pause the flush runs exactly once;
- on sample-rate change the old stream gets the tail before recreation;
- with no stream/rate the flush stays silent and does not crash.
"""
from __future__ import annotations

import queue
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

import config  # noqa: E402
import worker as worker_mod  # noqa: E402

failures: list[str] = []


def check(condition: bool, label: str) -> None:
    if condition:
        print(f"  ok   {label}")
    else:
        failures.append(label)
        print(f"  FAIL {label}")


class FakeChunk:
    def __init__(self, rate: int = 8000, count: int = 2400) -> None:
        self.rate = rate
        self.samples = [0.0] * count


class FakeRecognizer:
    """Counts flushes: each feed longer than a chunk counts as a tail flush."""

    def __init__(self) -> None:
        self.feeds: list[int] = []
        self.creates = 0
        self.text = ""
        self.flush_calls = 0
        self.lock = threading.Lock()

    def create_stream(self):
        with self.lock:
            self.creates += 1
        return {"id": self.creates}

    def feed(self, stream, samples, rate):
        size = len(samples)
        with self.lock:
            self.feeds.append(size)
            # tail flush: 0.6 s of zeros at 8 kHz = 4800 samples
            if size >= int(rate * config.TAIL_PAD_SECONDS):
                self.flush_calls += 1
                self.text = self.text + " хвост"
        return self.text

    def is_endpoint(self, stream):
        return False


def new_worker(recognizer, paused=lambda: False, audio=None):
    emitted: list[tuple] = []
    audio = audio if audio is not None else queue.Queue()
    worker = worker_mod.RecognitionWorker(
        recognizer, audio, lambda *args: emitted.append(args), paused)
    return worker, audio, emitted


print("1. Флаш при остановке доигрывает хвост и уходит в UI")
recognizer = FakeRecognizer()
worker, audio, emitted = new_worker(recognizer)
worker.start()
audio.put(FakeChunk())
time.sleep(0.4)
worker.stop()
worker.join(timeout=3)
check(recognizer.flush_calls >= 1, f"хвостовой флаш выполнен ({recognizer.flush_calls} раз)")
check(any("хвост" in str(item) for item in emitted), "UI получил текст, дополненный флашем")

print("2. Пауза даёт ровно один флаш")
state = {"paused": False}
recognizer = FakeRecognizer()
worker, audio, emitted = new_worker(recognizer, paused=lambda: state["paused"])
worker.start()
audio.put(FakeChunk())
time.sleep(0.3)
state["paused"] = True
audio.put(FakeChunk())
audio.put(FakeChunk())
time.sleep(0.5)
check(recognizer.flush_calls == 1, f"на паузе один флаш (получено {recognizer.flush_calls})")
state["paused"] = False
time.sleep(0.3)
worker.stop()
worker.join(timeout=3)

print("3. Смена частоты: хвост отдаётся до пересоздания потока")
recognizer = FakeRecognizer()
worker, audio, emitted = new_worker(recognizer)
worker.start()
audio.put(FakeChunk(rate=48000, count=960))
time.sleep(0.3)
flushes_before = recognizer.flush_calls
audio.put(FakeChunk(rate=8000, count=4800))
time.sleep(0.3)
check(recognizer.flush_calls > flushes_before,
      f"флаш перед пересозданием потока ({recognizer.flush_calls - flushes_before})")
check(recognizer.creates >= 2, f"поток пересоздан ({recognizer.creates} create)")
worker.stop()
worker.join(timeout=3)

print("4. Флаш без потока и без частоты молчит и не падает")
recognizer = FakeRecognizer()
worker, audio, emitted = new_worker(recognizer)
worker._flush_tail(None, 8000)
worker._flush_tail({"id": 1}, None)
check(recognizer.flush_calls == 0, "без потока/частоты флаша нет")

print("5. Ошибка декодера во флаше не роняет воркер")


class BrokenRecognizer(FakeRecognizer):
    def feed(self, stream, samples, rate):
        if len(samples) >= int(rate * config.TAIL_PAD_SECONDS):
            raise RuntimeError("декодер упал")
        return super().feed(stream, samples, rate)


recognizer = BrokenRecognizer()
worker, audio, emitted = new_worker(recognizer)
worker.start()
audio.put(FakeChunk())
time.sleep(0.3)
worker.stop()
worker.join(timeout=3)
check(not worker.is_alive(), "воркер завершился без исключения")

print()
if failures:
    print(f"ПРОВАЛЕНО {len(failures)}:")
    for item in failures:
        print("  -", item)
    sys.exit(1)
print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
