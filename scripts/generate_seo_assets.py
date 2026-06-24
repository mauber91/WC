#!/usr/bin/env python3
"""Generate og-image.png and apple-touch-icon.png for social / home-screen use."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "frontend" / "public"

FOREST = "#153d2b"
ACID = "#c7ff55"
MUTED = "#a8bdaf"
PAPER = "#f2f3ed"


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Georgia Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Georgia.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _draw_bracket_hint(draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
    left = width - 360
    top = 90
    col_w = 72
    row_h = 58
    color = "#2a5f45"
    for round_idx in range(4):
        x = left + round_idx * (col_w + 18)
        slots = 2 ** (3 - round_idx)
        gap = (row_h * 8) / slots
        for slot in range(slots):
            y = top + slot * gap + gap / 4
            box_h = max(18, gap / 2.4)
            draw.rounded_rectangle((x, y, x + col_w, y + box_h), radius=6, outline=color, width=2)


def generate_og_image(path: Path) -> None:
    width, height = 1200, 630
    image = Image.new("RGB", (width, height), FOREST)
    draw = ImageDraw.Draw(image)

    draw.ellipse((72, 168, 192, 288), fill=ACID)
    draw.text((108, 206), "26", fill=FOREST, font=_font(64, bold=True))

    draw.text((228, 196), "WC Knockout Predictor", fill=PAPER, font=_font(64, bold=True))
    draw.text((232, 286), "FIFA World Cup 2026", fill=MUTED, font=_font(34))
    draw.text(
        (232, 352),
        "Monte Carlo forecasts · live bracket · match probabilities",
        fill=MUTED,
        font=_font(24),
    )

    _draw_bracket_hint(draw, width, height)
    image.save(path, format="PNG", optimize=True)


def generate_apple_touch_icon(path: Path) -> None:
    size = 180
    image = Image.new("RGB", (size, size), FOREST)
    draw = ImageDraw.Draw(image)
    margin = 24
    draw.ellipse((margin, margin, size - margin, size - margin), fill=ACID)
    draw.text((58, 52), "26", fill=FOREST, font=_font(56, bold=True))
    image.save(path, format="PNG", optimize=True)


def main() -> None:
    PUBLIC.mkdir(parents=True, exist_ok=True)
    generate_og_image(PUBLIC / "og-image.png")
    generate_apple_touch_icon(PUBLIC / "apple-touch-icon.png")
    print(f"Wrote {PUBLIC / 'og-image.png'}")
    print(f"Wrote {PUBLIC / 'apple-touch-icon.png'}")


if __name__ == "__main__":
    main()
