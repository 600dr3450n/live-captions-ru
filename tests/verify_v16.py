#!/usr/bin/env python3
"""Проверка: текст живёт сплошным потоком, а затемнение идёт по таймеру.

Фраз больше нет. Пауза в речи не закрывает и не переносит текст, поэтому вид не
прыгает. Слово становится «прошлым» не потому, что оказалось на верхней строке, а
потому что с момента его распознавания прошло больше секунд, заданных в настройках
(«Держать слово ярким»). Тест проверяет обе стороны: окно подсветки сужается со
временем, а пауза границы не создаёт.
"""
from __future__ import annotations

import queue
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

from worker import RecognitionWorker  # noqa: E402

WINDOW = 1.5
failures = 0


def check(ok: bool, label: str) -> None:
    global failures
    print(f"  {'ok  ' if ok else 'ПРОВАЛ'} {label}")
    if not ok:
        failures += 1


class FakeStream:
    def __init__(self) -> None:
        self.text = ""
        self.phrase_ended = False
        self.phrase_frames = 0
        self.phrases = 0


class Chunk:
    rate = 8000

    def __init__(self) -> None:
        self.samples = [0.0] * 2400


class FakeRecognizer:
    """Отдаёт заранее заданные варианты текста, по одному на вызов feed."""

    def __init__(self, texts: list[str], pause_every: int = 2) -> None:
        self._texts = list(texts)
        self._calls = 0
        self._pause_every = pause_every

    def create_stream(self) -> FakeStream:
        return FakeStream()

    def feed(self, stream: FakeStream, samples, rate=None) -> str:
        index = min(self._calls, len(self._texts) - 1)
        self._calls += 1
        stream.text = self._texts[index]
        # Модель охотно сообщает о паузе: если бы вид зависел от неё, это всплыло бы.
        if self._pause_every and self._calls % self._pause_every == 0:
            stream.phrase_ended = True
            stream.phrase_frames = 30
            stream.phrases += 1
        return stream.text

    def feed_no_read(self, stream: FakeStream, samples, rate=None) -> None:
        self.feed(stream, samples, rate)

    def text(self, stream: FakeStream) -> str:
        return stream.text

    def is_endpoint(self, stream: FakeStream) -> bool:
        return True


def run(texts: list[str], gap: float, room: int = 6) -> list[tuple[str, int, int, int]]:
    """Прогон с паузами между чанками: собираем всё, что ушло в UI."""
    seen: list[tuple[str, int, int, int]] = []
    audio: queue.Queue = queue.Queue()

    worker = RecognitionWorker(
        FakeRecognizer(texts),
        audio,
        lambda text, confirmed, start, end: seen.append((text, confirmed, start, end)),
        lambda: False,
        highlight_seconds=lambda: WINDOW,
    )
    worker.start()
    try:
        for _ in range(room):
            audio.put(Chunk())
            time.sleep(gap)
    finally:
        worker.stop()
        worker.join(timeout=3)
    return seen


print("1. Паузы не создают границ: текст остаётся одним потоком")
seen = run(["раз", "раз два", "раз два три"], gap=0.25)
texts = [text for text, _c, _s, _e in seen]
check(bool(texts) and texts[-1].count(" ") >= 2, f"текст накапливается: {texts[-1] if texts else ''!r}")
check(all(t.split()[0] == "раз" for t in texts if t), "начало текста не теряется")

print("2. Окно подсветки сужается по таймеру")
audio: queue.Queue = queue.Queue()
worker = RecognitionWorker(
    FakeRecognizer(["один два три четыре"]),
    audio,
    lambda *args: None,
    lambda: False,
    highlight_seconds=lambda: WINDOW,
)
worker.start()
try:
    audio.put(Chunk())
    time.sleep(0.6)  # последнее слово успевает осесть (WORD_SETTLE_SECONDS)
    first = worker._highlight_range("один два три четыре")  # noqa: SLF001
    time.sleep(WINDOW + 0.2)
    second = worker._highlight_range("один два три четыре")  # noqa: SLF001
finally:
    worker.stop()
    worker.join(timeout=3)

print(f"  окно сразу: {first}, через {WINDOW + 0.8:.2f} с: {second}")
check(first[1] == 4, f"все слова подтверждены: {first}")
check(second[0] == second[1] or second[0] > first[0],
      f"ярких слов стало меньше: было {first[0]}..{first[1]}, стало {second[0]}..{second[1]}")

print("3. Слово переживает паузу и не пропадает из текста")
seen = run(["проверка паузы"], gap=0.45, room=4)
check(bool(seen) and "паузы" in seen[-1][0], f"текст после паузы: {seen[-1][0] if seen else ''!r}")

print("\nВСЕ ПРОВЕРКИ ПРОЙДЕНЫ" if failures == 0 else f"\nПРОВАЛОВ: {failures}")
raise SystemExit(1 if failures else 0)
