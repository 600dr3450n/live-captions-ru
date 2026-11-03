"""Check of utterance-splitting logic in the worker thread (with a fake recognizer)."""
from __future__ import annotations

import queue
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np

APP_DIR = Path(__file__).resolve().parent.parent / "app"
sys.path.insert(0, str(APP_DIR))

import main as app_main  # noqa: E402


class FakeRecognizer:
    """Returns a predefined sequence of hypotheses."""

    def __init__(self, script: list[tuple[str, bool]]) -> None:
        self.script = script
        self.index = -1
        self.streams_created = 0
        self.reset_calls = 0

    def create_stream(self):
        self.streams_created += 1
        return object()

    def feed(self, stream, samples, rate) -> str:
        if self.index + 1 < len(self.script):
            self.index += 1
        return self.script[max(0, self.index)][0]

    def is_endpoint(self, stream) -> bool:
        return self.script[max(0, self.index)][1]

    def reset(self, stream) -> None:
        self.reset_calls += 1

    def finish(self, stream) -> str:
        return ""


def drive(script: list[tuple[str, bool]], repeats: int = 2) -> tuple[list[tuple], FakeRecognizer]:
    recognizer = FakeRecognizer(script)
    audio: "queue.Queue" = queue.Queue()
    states: list[tuple] = []
    worker = app_main.RecognitionWorker(recognizer, audio, lambda *args: states.append(args), lambda: False)
    worker.start()
    chunk = SimpleNamespace(samples=np.zeros(960, dtype=np.float32), rate=48000)
    for _ in range(len(script) * repeats):
        audio.put(chunk)
        time.sleep(0.12)  # worker refreshes the screen no more often than every 80 ms
    time.sleep(0.3)
    worker.stop()
    worker.join(timeout=2.0)
    return states, recognizer


def main() -> int:
    ok = True

    print("=== Сценарий 1: реплика, пауза, продолжение (без склейки) ===")
    script = [
        ("сейчас к тебе приедет бригада давай", False),
        ("сейчас к тебе приедет бригада давай", True),
        ("сейчас к тебе приедет бригада давай давай я жду", True),
        ("сейчас к тебе приедет бригада давай давай я жду", False),
        ("сейчас к тебе приедет бригада давай давай я жду", False),
    ]
    states, recognizer = drive(script)
    history, phrase_text, complete, start, _end = states[-1]
    active = phrase_text.split()
    print(f"  история: {list(history)}")
    print(f"  активная строка: {active}")
    print(f"  создано потоков: {recognizer.streams_created}, сбросов: {recognizer.reset_calls}")
    history_ok = list(history)[-1:] == ["сейчас к тебе приедет бригада давай"] if history else False
    active_ok = active == ["давай", "я", "жду"]
    no_glue = not any(word.endswith("я") and len(word) > 4 for word in active)
    highlight_ok = complete <= len(active) and start <= complete
    print(f"  фраза ушла в историю: {'ок' if history_ok else 'ОШИБКА'}")
    print(f"  продолжение без склейки: {'ок' if active_ok and no_glue else 'ОШИБКА'}")
    print(f"  диапазон подсветки: {start}..{complete} из {len(active)} — {'ок' if highlight_ok else 'ОШИБКА'}")
    ok = ok and history_ok and active_ok and no_glue and highlight_ok

    print("\n=== Сценарий 2: модель переписала уже отданный текст ===")
    script2 = [
        ("привет как дела", False),
        ("привет как дела", True),
        ("привет", False),
        ("привет друг", False),
    ]
    states2, recognizer2 = drive(script2)
    print(f"  создано потоков: {recognizer2.streams_created} (ожидалось > 1 — сработал откат)")
    print(f"  последнее состояние: {states2[-1]}")
    fallback_ok = recognizer2.streams_created > 1
    print(f"  откат при переписывании: {'ок' if fallback_ok else 'ОШИБКА'}")
    ok = ok and fallback_ok

    print("\n=== ИТОГ ===")
    print("  все проверки пройдены" if ok else "  есть ошибки")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
