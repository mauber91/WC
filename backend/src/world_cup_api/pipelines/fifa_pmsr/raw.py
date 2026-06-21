from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import pdfplumber
from pypdf import PdfReader

from world_cup_api.pipelines.fifa_pmsr.classify import classify_page
from world_cup_api.pipelines.fifa_pmsr.render import render_pages
from world_cup_api.pipelines.fifa_pmsr.types import RawPage


LOGGER = logging.getLogger(__name__)
MAX_INLINE_IMAGE_BYTES = 0


def _primitive(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return {"byte_length": len(value), "sha256": hashlib.sha256(value).hexdigest()}
    if isinstance(value, (list, tuple)):
        return [_primitive(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _primitive(item) for key, item in value.items() if key != "stream"}
    return str(value)


def _bbox(item: dict[str, Any]) -> list[float] | None:
    keys = ("x0", "top", "x1", "bottom")
    if all(key in item and item[key] is not None for key in keys):
        return [round(float(item[key]), 4) for key in keys]
    return None


def _payload_checksum(elements: list[dict[str, Any]]) -> str:
    encoded = json.dumps(elements, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def payload_checksum(elements: list[dict[str, Any]]) -> str:
    return _payload_checksum(elements)


def _extract_tables(page: Any, page_number: int) -> list[dict[str, Any]]:
    cells: list[dict[str, Any]] = []
    try:
        for table_index, table in enumerate(page.find_tables()):
            extracted = table.extract()
            for row_index, row in enumerate(table.rows):
                for column_index, cell_bbox in enumerate(row.cells):
                    value = None
                    if row_index < len(extracted) and column_index < len(extracted[row_index]):
                        value = extracted[row_index][column_index]
                    element_id = f"p{page_number}:table:{table_index}:r{row_index}:c{column_index}"
                    cells.append(
                        {
                            "id": element_id,
                            "table_index": table_index,
                            "row_index": row_index,
                            "column_index": column_index,
                            "text": value,
                            "bbox": _primitive(cell_bbox),
                            "classification": "mapped",
                            "mapped_by": "pdf_table_geometry",
                        }
                    )
    except Exception as exc:
        LOGGER.warning("table extraction failed on page %s: %s", page_number, exc)
    return cells


def _extract_images(reader_page: Any, page_number: int, image_dir: Path) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    image_dir.mkdir(parents=True, exist_ok=True)
    try:
        images = list(reader_page.images)
    except Exception as exc:
        LOGGER.warning("embedded image enumeration failed on page %s: %s", page_number, exc)
        return output
    for index, image_file in enumerate(images):
        data = image_file.data
        suffix = Path(image_file.name).suffix or ".bin"
        target = image_dir / f"page-{page_number:03d}-{index:03d}{suffix}"
        target.write_bytes(data)
        output.append(
            {
                "id": f"p{page_number}:image:{index}",
                "name": image_file.name,
                "uri": str(target.resolve()),
                "byte_length": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "classification": "mapped",
                "mapped_by": "embedded_image_capture",
            }
        )
    return output


def extract_raw_pages(pdf_path: str | Path, artifact_dir: str | Path) -> list[RawPage]:
    source = Path(pdf_path)
    root = Path(artifact_dir)
    render_info = render_pages(source, root / "renders")
    image_dir = root / "images"
    reader = PdfReader(source)
    raw_pages: list[RawPage] = []

    with pdfplumber.open(source) as plumber:
        page_count = len(plumber.pages)
        for index, page in enumerate(plumber.pages):
            page_number = index + 1
            reader_page = reader.pages[index]
            try:
                raw_text = reader_page.extract_text(extraction_mode="layout") or ""
            except Exception:
                raw_text = reader_page.extract_text() or ""
            classification = classify_page(raw_text, page_number, page_count)

            chars: list[dict[str, Any]] = []
            for char_index, char in enumerate(page.chars):
                text = str(char.get("text", ""))
                private_use = any(0xE000 <= ord(codepoint) <= 0xF8FF for codepoint in text)
                chars.append(
                    {
                        "id": f"p{page_number}:char:{char_index}",
                        "text": text,
                        "glyph_codes": [f"U+{ord(codepoint):04X}" for codepoint in text],
                        "bbox": _bbox(char),
                        "fontname": char.get("fontname"),
                        "size": _primitive(char.get("size")),
                        "matrix": _primitive(char.get("matrix")),
                        "stroking_color": _primitive(char.get("stroking_color")),
                        "non_stroking_color": _primitive(char.get("non_stroking_color")),
                        "classification": "unresolved" if private_use else "mapped",
                        "mapped_by": None if private_use else "raw_text_capture",
                    }
                )

            words: list[dict[str, Any]] = []
            try:
                extracted_words = page.extract_words(
                    keep_blank_chars=False,
                    use_text_flow=False,
                    extra_attrs=["fontname", "size"],
                )
            except Exception:
                extracted_words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
            for word_index, word in enumerate(extracted_words):
                words.append(
                    {
                        "id": f"p{page_number}:word:{word_index}",
                        "text": word.get("text", ""),
                        "bbox": _bbox(word),
                        "fontname": word.get("fontname"),
                        "size": _primitive(word.get("size")),
                        "direction": word.get("direction"),
                        "classification": "mapped",
                        "mapped_by": "raw_text_span_capture",
                    }
                )

            vectors: list[dict[str, Any]] = []
            for kind in ("lines", "rects", "curves"):
                for vector_index, vector in enumerate(getattr(page, kind, [])):
                    vector_data = _primitive(vector)
                    vector_data.update(
                        id=f"p{page_number}:{kind[:-1]}:{vector_index}",
                        primitive_type=kind[:-1],
                        bbox=_bbox(vector),
                        classification=(
                            "decorative"
                            if classification.page_type.endswith("section")
                            or classification.page_type in {"cover", "closing_artwork"}
                            else "mapped"
                        ),
                        mapped_by="raw_vector_capture",
                    )
                    vectors.append(vector_data)

            images = _extract_images(reader_page, page_number, image_dir)
            plumber_images = list(page.images)
            for image_index, image_meta in enumerate(plumber_images):
                positioned = {
                    "pdfplumber_image_index": image_index,
                    "bbox": _bbox(image_meta),
                    "x0": _primitive(image_meta.get("x0")),
                    "top": _primitive(image_meta.get("top")),
                    "x1": _primitive(image_meta.get("x1")),
                    "bottom": _primitive(image_meta.get("bottom")),
                    "width": _primitive(image_meta.get("width")),
                    "height": _primitive(image_meta.get("height")),
                    "colorspace": _primitive(image_meta.get("colorspace")),
                    "bits": _primitive(image_meta.get("bits")),
                }
                if image_index < len(images):
                    images[image_index].update(positioned)
                else:
                    images.append(
                        {
                            "id": f"p{page_number}:image-meta:{image_index}",
                            **positioned,
                            "classification": "mapped",
                            "mapped_by": "embedded_image_geometry",
                        }
                    )
            if classification.page_type.endswith("section") or classification.page_type in {
                "cover",
                "closing_artwork",
            }:
                for image in images:
                    image["classification"] = "decorative"
                    image["mapped_by"] = "decorative_artwork"

            payloads = {
                "glyphs": chars,
                "text_spans": words,
                "vectors": vectors,
                "images": images,
                "table_cells": _extract_tables(page, page_number),
            }
            raw_pages.append(
                RawPage(
                    page_number=page_number,
                    width_points=float(page.width),
                    height_points=float(page.height),
                    rotation=int(page.rotation or 0),
                    raw_text=raw_text,
                    render_uri=render_info[index][0],
                    render_sha256=render_info[index][1],
                    classification=classification,
                    payloads=payloads,
                )
            )
    return raw_pages
