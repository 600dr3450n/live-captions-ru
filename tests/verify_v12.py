"""Проверка эталонного settings.json на момент релиза 1.0.1.

Схема сверена с фактическим файлом (43 поля). Проверяем типы и диапазоны того,
что реально пишется на диск, roundtrip, совместимость со старым файлом и то, что
чужие значения не роняют загрузку.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

import settings as st  # noqa: E402

failures: list[str] = []


def check(condition: bool, label: str) -> None:
    if condition:
        print(f"  ok   {label}")
    else:
        failures.append(label)
        print(f"  FAIL {label}")


def schema_of_file(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    print(f"  файл: {path.name}, {len(json.dumps(data))} байт, версия {data.get('version')}")

    a = data["appearance"]
    check(isinstance(a["font_size_px"], int) and 8 <= a["font_size_px"] <= 96, "font_size_px int в 8..96")
    check(isinstance(a["line_spacing"], float) and 0.8 <= a["line_spacing"] <= 2.0, "line_spacing float в 0.8..2.0")
    check(isinstance(a["letter_spacing"], float), "letter_spacing float")
    check(isinstance(a["outline_width"], float) and 0.0 <= a["outline_width"] <= 12.0, "outline_width float в 0..12")
    check(isinstance(a["font_family"], str) and a["font_family"], "font_family непустая строка")
    for key in ("text_color", "outline_color", "backdrop_color"):
        value = a[key]
        check(isinstance(value, str) and value.startswith("#") and len(value) in (7, 9), f"{key} строка цвета")
    for key in ("bold", "italic", "outline_enabled", "backdrop_enabled", "shadow", "uppercase"):
        check(isinstance(a[key], bool), f"{key} bool")
    for key in ("text_transparency", "outline_transparency", "tail_transparency", "history_transparency",
                "backdrop_transparency", "corner_radius", "padding_x", "padding_y", "shadow_size"):
        check(isinstance(a[key], int) and 0 <= a[key] <= 255, f"{key} int в 0..255")
    check(a["align"] in ("left", "center", "right"), "align допустимое значение")

    g = data["geometry"]
    check(g["position"] in ("top", "bottom", "custom", "free"), "geometry.position допустимое")
    check(isinstance(g["width_percent"], int) and 10 <= g["width_percent"] <= 100, "width_percent int в 10..100")
    check(isinstance(g["max_lines"], int) and 1 <= g["max_lines"] <= 5, "max_lines int в 1..5")
    for key in ("x", "y", "margin", "monitor", "width_px"):
        check(isinstance(g[key], int), f"geometry.{key} int")
    check(isinstance(g["avoid_taskbar"], bool), "avoid_taskbar bool")

    b = data["behaviour"]
    check(isinstance(b["highlight_seconds"], (int, float)) and 0 < b["highlight_seconds"] <= 10,
          "highlight_seconds в 0..10")
    check(isinstance(b["idle_clear_sec"], (int, float)) and b["idle_clear_sec"] >= 0, "idle_clear_sec число >= 0")
    check(isinstance(b["highlight_seconds"], float) and 0.5 <= b["highlight_seconds"] <= 10.0,
          "highlight_seconds float в 0.5..10")
    check(isinstance(b["autostart"], bool), "behaviour.autostart bool")
    check(isinstance(b["start_visible"], bool), "behaviour.start_visible bool")

    au = data["audio"]
    check(isinstance(au["device"], str), "audio.device строка")
    check(isinstance(au["threads"], int) and au["threads"] >= 1, "audio.threads int >= 1")
    check(isinstance(data["version"], int), "version int")


print("1. Дефолтные настройки: что реально попадает в файл")
with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp) / "settings.json"
    original = st.settings_path
    st.settings_path = lambda: tmp_path  # type: ignore[assignment]
    try:
        st.save_settings(st.Settings().validated())
        schema_of_file(tmp_path)

        print("2. Roundtrip: load(save(default)) совпадает с дефолтом")
        loaded = st.load_settings()
        check(loaded == st.Settings().validated(), "roundtrip без расхождений")

        print("3. Файл от старой версии (схема без новых полей)")
        tmp_path.write_text(json.dumps({
            "version": 1,
            "appearance": {"font_size_px": 28, "text_color": "#FFEE00"},
            "geometry": {"position": "top"},
            "behaviour": {"highlight_seconds": 3},
        }), encoding="utf-8")
        old = st.load_settings()
        st.save_settings(old)
        saved_version = json.loads(tmp_path.read_text(encoding="utf-8"))["version"]
        check(saved_version == st.SETTINGS_VERSION, "при сохранении версия файла поднята до текущей")
        check(old.appearance.font_size_px == 28, "старое значение сохранено")
        check(isinstance(old.audio.threads, int) and old.audio.threads >= 1, "новое поле получило валидный дефолт")
        check(old.geometry.position == "top", "старая геометрия сохранена")

        print("4. Чужие типы в файле: приложение не падает")
        tmp_path.write_text(json.dumps({
            "version": "десять",
            "appearance": {"line_spacing": "много", "font_size_px": "большой", "text_color": "red",
                           "bold": "да"},
            "audio": {"device": 42, "threads": None},
        }), encoding="utf-8")
        weird = st.load_settings()
        check(isinstance(weird.appearance.line_spacing, float), "line_spacing стал числом")
        check(isinstance(weird.appearance.font_size_px, int), "font_size_px стал числом")
        check(weird.appearance.text_color.startswith("#"), "текстовый цвет стал корректным")
        check(weird.audio.device == "" and isinstance(weird.audio.threads, int), "audio приведён к типам")

        print("5. Обрезанный файл: дефолты и карантин")
        tmp_path.write_text('{"appearance": {"font_size_px": 30, ', encoding="utf-8")
        broken = st.load_settings()
        check(broken == st.Settings().validated(), "загружены дефолты")
        check(tmp_path.with_suffix(".json.broken").exists(), "файл отложен в .broken")
    finally:
        st.settings_path = original  # type: ignore[assignment]

print()
if failures:
    print(f"ПРОВАЛЕНО {len(failures)}:")
    for item in failures:
        print("  -", item)
    sys.exit(1)
print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
