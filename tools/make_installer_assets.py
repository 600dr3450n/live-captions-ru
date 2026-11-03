#!/usr/bin/env python3
"""Картинки мастера установки из иконки приложения.

Для classic-стиля Inno Setup: слева крупный баббл на белом фоне, в правом
верхнем углу тот же баббл на прозрачном фоне. Без надписей.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "installer" / "assets"
ICON = ROOT / "app" / "icon.ico"

WHITE = (255, 255, 255, 255)


def icon_rgba(px: int) -> Image.Image:
    """Иконка приложения нужного размера, обрезанная по непрозрачным краям."""
    image = Image.open(ICON)
    image.size = (256, 256)
    image = image.convert("RGBA")
    box = image.getbbox()
    if box:
        image = image.crop(box)
    return image.resize((px, px), Image.LANCZOS)


def wizard() -> None:
    """Левая панель мастера: соотношение 164:314, черный баббл на белом."""
    width, height = 404, 772
    canvas = Image.new("RGBA", (width, height), WHITE)
    margin = 18
    size = width - margin * 2
    badge = icon_rgba(size)
    canvas.paste(badge, ((width - size) // 2, (height - size) // 2), badge)
    canvas.convert("RGB").save(OUT / "wizard.png")
    print("wizard", canvas.size, "->", OUT / "wizard.png")


def small() -> None:
    """Правый верхний угол: тот же баббл на прозрачном фоне."""
    size = 256
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    badge = icon_rgba(size)
    canvas.paste(badge, (0, 0), badge)
    canvas.save(OUT / "wizard-small.png")
    print("small", canvas.size, "->", OUT / "wizard-small.png")


def drop_stale() -> None:
    """Убирает прежние bmp и фон, которых больше нет в установщике."""
    for name in ("wizard.bmp", "wizard-back.bmp", "wizard-back.png", "wizard-small.bmp"):
        path = OUT / name
        if path.exists():
            path.unlink()
            print("удален", name)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    drop_stale()
    wizard()
    small()
