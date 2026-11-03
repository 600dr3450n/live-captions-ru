"""Проверка защиты от двойного запуска (именованный мьютекс)."""
from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "app"
sys.path.insert(0, str(APP_DIR))

import main  # noqa: E402


def test_single_instance_guard() -> None:
    """The first call creates the mutex, the second one has to see it.

    As a plain script this printed the verdict and exit code instead of asserting, so
    pytest collected nothing and a broken guard still looked like a green run.
    """
    first = main.already_running()
    second = main.already_running()
    print(f"первый вызов (мьютекса не было): {first} — ожидалось False")
    print(f"второй вызов (мьютекс уже создан): {second} — ожидалось True")
    assert first is False, "первый вызов должен создать мьютекс"
    assert second is True, "второй вызов должен увидеть занятый мьютекс"


if __name__ == "__main__":
    test_single_instance_guard()
    print("РЕЗУЛЬТАТ: логика верна")
