from __future__ import annotations

import re
from pathlib import Path

import pytesseract
from PIL import Image


def ocr_numeric_bbox(
    render_uri: str | Path,
    bbox: list[float],
    page_width: float,
    page_height: float,
) -> tuple[float | None, float]:
    """Run constrained OCR over one numeric cell, never over an entire page."""
    with Image.open(render_uri) as image:
        scale_x = image.width / page_width
        scale_y = image.height / page_height
        padding = 4
        crop_box = (
            max(0, int(bbox[0] * scale_x) - padding),
            max(0, int(bbox[1] * scale_y) - padding),
            min(image.width, int(bbox[2] * scale_x) + padding),
            min(image.height, int(bbox[3] * scale_y) + padding),
        )
        crop = image.crop(crop_box).resize(
            ((crop_box[2] - crop_box[0]) * 3, (crop_box[3] - crop_box[1]) * 3)
        )
        data = pytesseract.image_to_data(
            crop,
            config="--psm 7 -c tessedit_char_whitelist=0123456789.-",
            output_type=pytesseract.Output.DICT,
        )
    candidates: list[tuple[str, float]] = []
    for text, confidence in zip(data["text"], data["conf"], strict=False):
        cleaned = text.strip().replace(",", "")
        if re.fullmatch(r"-?\d+(?:\.\d+)?", cleaned):
            candidates.append((cleaned, max(0.0, float(confidence)) / 100))
    if not candidates:
        return None, 0.0
    value, confidence = max(candidates, key=lambda candidate: candidate[1])
    return float(value), confidence
