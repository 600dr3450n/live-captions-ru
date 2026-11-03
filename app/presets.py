"""Ready-made appearance styles, applied as a whole."""
from __future__ import annotations

from dataclasses import dataclass

from settings import Settings


@dataclass(frozen=True)
class Style:
    """One preset: a name and the appearance/geometry values it sets."""

    key: str
    title: str
    appearance: dict
    geometry: dict


STYLES: tuple[Style, ...] = (
    Style(
        key="default",
        title="По умолчанию",
        appearance={
            "font_size_px": 24,
            "bold": True,
            "italic": False,
            "uppercase": True,
            "align": "left",
            "line_spacing": 1.0,
            "letter_spacing": 0.0,
            "text_color": "#FFFFFF",
            "text_transparency": 0,
            "history_transparency": 40,
            "tail_transparency": 40,
            "outline_enabled": True,
            "outline_width": 1.0,
            "outline_color": "#000000",
            "outline_transparency": 20,
            "backdrop_enabled": True,
            "backdrop_color": "#000000",
            "backdrop_transparency": 40,
            "padding_x": 12,
            "padding_y": 12,
            "corner_radius": 6,
        },
        geometry={"position": "bottom", "width_percent": 40, "width_px": 0, "max_lines": 2},
    ),
    Style(
        key="minimal",
        title="Минималистичный",
        appearance={
            "font_size_px": 12,
            "bold": False,
            "italic": False,
            "uppercase": True,
            "align": "left",
            "line_spacing": 1.0,
            "letter_spacing": 0.0,
            "text_color": "#000000",
            "text_transparency": 0,
            "history_transparency": 0,
            "tail_transparency": 0,
            "outline_enabled": False,
            "outline_width": 1.0,
            "outline_color": "#8C8C8C",
            "outline_transparency": 20,
            "backdrop_enabled": False,
            "backdrop_color": "#FFFFFF",
            "backdrop_transparency": 40,
            "padding_x": 2,
            "padding_y": 2,
            "corner_radius": 0,
        },
        geometry={"position": "custom", "width_percent": 25, "width_px": 0, "max_lines": 1},
    ),
    Style(
        key="contrast",
        title="Крупный контрастный",
        appearance={
            "font_size_px": 40,
            "bold": True,
            "italic": False,
            "uppercase": True,
            "align": "left",
            "line_spacing": 1.0,
            "letter_spacing": 0.0,
            "text_color": "#7DF9FF",
            "text_transparency": 0,
            "history_transparency": 0,
            "tail_transparency": 40,
            "outline_enabled": True,
            "outline_width": 2.0,
            "outline_color": "#000000",
            "outline_transparency": 20,
            "backdrop_enabled": True,
            "backdrop_color": "#000000",
            "backdrop_transparency": 20,
            "padding_x": 18,
            "padding_y": 18,
            "corner_radius": 9,
        },
        geometry={"position": "bottom", "width_percent": 60, "width_px": 0, "max_lines": 2},
    ),
)


def style_by_key(key: str) -> Style | None:
    return next((style for style in STYLES if style.key == key), None)


def apply_style(settings: Settings, key: str) -> Style | None:
    """Copy a preset into the settings object; returns the applied style."""
    style = style_by_key(key)
    if style is None:
        return None
    for name, value in style.appearance.items():
        setattr(settings.appearance, name, value)
    for name, value in style.geometry.items():
        setattr(settings.geometry, name, value)
    settings.validated()
    return style
