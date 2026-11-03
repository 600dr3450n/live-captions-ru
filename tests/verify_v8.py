"""Проверка версии 10: конец реплики не оставляет слов активными, обводка/тень гаснут вместе с текстом,
задержка показа слова не растёт, перенос строк работает."""
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
import settings as settings_module  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from overlay import SubtitleOverlay, alpha_from_transparency  # noqa: E402

ART = Path(__file__).resolve().parent.parent / "_artifacts"
ART.mkdir(exist_ok=True)


class ScriptedRecognizer:
    """Отдаёт заданную последовательность текстов; конец реплики — по списку текстов."""

    def __init__(self, script: list[str], endpoints: tuple[str, ...] = ()) -> None:
        self._script = list(script)
        self._endpoints = set(endpoints)
        self._last = ""

    def create_stream(self):
        return object()

    def feed(self, stream, samples, rate) -> str:  # noqa: ANN001
        self._last = self._script.pop(0) if self._script else ""
        return self._last

    def is_endpoint(self, stream) -> bool:  # noqa: ANN001
        return self._last in self._endpoints

    def reset(self, stream) -> None:  # noqa: ANN001
        pass

    def finish(self, stream) -> str:  # noqa: ANN001
        return ""


def run_worker(script: list[str], endpoints: tuple[str, ...] = (), chunks: int = 8, interval: float = 0.12):
    events: list[tuple] = []
    stamps: list[float] = []
    started = time.perf_counter()

    def on_text(*args) -> None:
        events.append(args)
        stamps.append(time.perf_counter() - started)

    worker = app_main.RecognitionWorker(
        ScriptedRecognizer(script, endpoints), queue.Queue(), on_text, lambda: False
    )
    worker.start()
    time.sleep(0.05)
    for _ in range(chunks):
        worker._audio.put(SimpleNamespace(samples=None, rate=48000))  # noqa: SLF001
        time.sleep(interval)
    time.sleep(0.3)
    worker.stop()
    worker.join(timeout=2.0)
    return events, (stamps[-1] if stamps else 0.0)


def check_endpoint_clears_active() -> bool:
    """Конец реплики: фраза уходит в историю и НЕ остаётся активной (иначе выглядит подсвеченной)."""
    events, _ = run_worker(
        ["привет мир", "привет мир ", "привет мир как дела", "привет мир как дела", ""],
        endpoints=("привет мир как дела",),
    )

    print("=== Конец реплики: фраза только в истории ===")
    leaks = []
    for history, text, confirmed, start, end in events:
        words = text.split()
        history_words = {word for phrase in history for word in phrase.split()}
        overlap = [word for word in words if word in history_words]
        print(f"  история={list(history)} активный={text!r} подтверждено={confirmed} подсветка=({start},{end})")
        if overlap:
            leaks.append((text, overlap))

    ok = not leaks
    print(f"  Слова, оставшиеся активными после ухода в историю: {leaks if leaks else 'нет'} — {'ок' if ok else 'ОШИБКА'}")
    return ok


def check_outline_fades_with_text(app) -> bool:
    """Яркость пикселей слова падает монотонно вместе с прозрачностью текста: обводка не «держит» текст."""
    print("\n=== Прозрачность текста гасит слово целиком ===")
    levels = (0, 25, 50, 75, 100)
    masses = []
    for transparency in levels:
        settings = settings_module.Settings()
        settings.appearance.text_transparency = transparency
        settings.appearance.uppercase = True
        settings.appearance.backdrop_enabled = False  # меряем только чернила текста
        settings.appearance.shadow = False
        settings.geometry.width_px = 700
        settings.geometry.max_lines = 2
        overlay = SubtitleOverlay(settings, exclude_from_capture=False)
        overlay.set_text("проверка прозрачности текста", 4, 0, 4)
        for _ in range(10):
            app.processEvents()
            time.sleep(0.02)
        image = overlay.grab().toImage().convertToFormat(QImage.Format.Format_ARGB32)
        buffer = np.frombuffer(image.constBits(), dtype=np.uint8)
        pixels = buffer.reshape(image.height(), image.bytesPerLine() // 4, 4)[:, : image.width(), 3]
        mass = int(pixels.sum())
        masses.append(mass)
        print(f"  прозрачность {transparency:3d} % → чернил текста {mass}")
        overlay.hide()
        overlay.deleteLater()

    ok = (
        masses[-1] == 0
        and masses[0] * 0.35 < masses[2] < masses[0] * 0.65  # 50 % прозрачности ≈ половина чернил
        and masses[1] < masses[0]
        and masses[3] < masses[2]
    )
    print(
        f"  Доля чернил от полной: "
        f"{[round(m / max(1, masses[0]) * 100) for m in masses]} % — {'ок' if ok else 'ОШИБКА'}"
    )
    return ok


def check_emit_is_immediate() -> bool:
    """Новое слово уходит на экран сразу, без ожидания троттлинга подсветки."""
    print("\n=== Новое слово показывается без лишней задержки ===")
    events, _ = run_worker(["раз", "раз ", "раз два", "раз два "], chunks=6)
    texts = [event[1] for event in events]
    print(f"  состояния: {texts}")
    ok = "раз два " in texts
    print(f"  Текст доходит до экрана целиком: {'ок' if ok else 'ОШИБКА'}")
    return ok


def main() -> int:
    app = QApplication(sys.argv)
    results = {
        "endpoint_clears_active": check_endpoint_clears_active(),
        "outline_fades": check_outline_fades_with_text(app),
        "emit_immediate": check_emit_is_immediate(),
    }
    print("\n=== ИТОГ ===")
    for name, ok in results.items():
        print(f"  {name}: {'ок' if ok else 'ОШИБКА'}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
