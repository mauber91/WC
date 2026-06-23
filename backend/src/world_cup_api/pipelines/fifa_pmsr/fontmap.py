from __future__ import annotations

import hashlib
import json
from pathlib import Path

from world_cup_api.pipelines.fifa_pmsr.extractors.core import PUA_DIGIT_MAP
from world_cup_api.pipelines.fifa_pmsr.types import RawPage


def font_checksum(font_name: str | None) -> str:
    return hashlib.sha256((font_name or "unknown-font").encode("utf-8")).hexdigest()


def write_font_map_registry(pages: list[RawPage], output_path: str | Path) -> Path:
    fonts: dict[str, dict[str, object]] = {}
    for page in pages:
        for glyph in page.payloads.get("glyphs", []):
            text = str(glyph.get("text", ""))
            if not any(character in PUA_DIGIT_MAP for character in text):
                continue
            name = str(glyph.get("fontname") or "unknown-font")
            checksum = font_checksum(name)
            fonts.setdefault(
                checksum,
                {
                    "font_name": name,
                    "font_checksum": checksum,
                    "mapping": {f"U+{ord(key):04X}": value for key, value in PUA_DIGIT_MAP.items()},
                    "source": "verified_fifa_pmsr_glyph_map",
                },
            )
    target = Path(output_path)
    target.write_text(json.dumps({"fonts": fonts}, indent=2, sort_keys=True), encoding="utf-8")
    return target
