from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from world_cup_api.pipelines.fifa_pmsr.template import load_template
from world_cup_api.pipelines.fifa_pmsr.types import DocumentManifest


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_metadata(metadata: Any) -> dict[str, Any]:
    if metadata is None:
        return {}
    return {str(key).lstrip("/"): str(value) for key, value in metadata.items() if value is not None}


def _cover_fields(text: str) -> dict[str, Any]:
    cleaned = text.replace("\x00", "f")
    versus = re.search(
        r"(?P<home>[A-Za-z .'-]+?)\s*(?P<hscore>\d+)\s*-\s*(?P<ascore>\d+)\s*\n\s*(?P<away>[A-Za-z .'-]+?)\s*(?:\n|Group)",
        cleaned,
    )
    match_no = re.search(r"Match\s+(\d+)", cleaned, flags=re.IGNORECASE)
    date = re.search(r"(\d{1,2}\s+[A-Za-z]+\s+20\d{2})", cleaned)
    kickoff = re.search(r"(\d{1,2}:\d{2})\s+Kick", cleaned, flags=re.IGNORECASE)
    venue = re.search(r"Kick\s+O[f]+\s*\n?\s*([^\n]+?(?:Stadium|Arena))", cleaned, flags=re.IGNORECASE)
    fields: dict[str, Any] = {
        "official_match_number": int(match_no.group(1)) if match_no else None,
        "match_date": date.group(1) if date else None,
        "kickoff_time": kickoff.group(1) if kickoff else None,
        "venue": venue.group(1).strip() if venue else None,
    }
    if versus:
        fields.update(
            home_team=versus.group("home").strip(),
            away_team=versus.group("away").strip(),
            home_score=int(versus.group("hscore")),
            away_score=int(versus.group("ascore")),
        )
    return fields


def inspect_report(path: str | Path) -> DocumentManifest:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if source.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a PDF file: {source}")

    reader = PdfReader(source)
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as exc:  # pragma: no cover - vendor-specific encryption
            raise ValueError("Encrypted PDF cannot be read without a password") from exc

    page_sizes = [
        [round(float(page.mediabox.width), 3), round(float(page.mediabox.height), 3)]
        for page in reader.pages
    ]
    texts = [(page.extract_text() or "") for page in reader.pages]
    joined = "\n".join(texts)
    template = load_template()
    expected_width, expected_height = template.config["page_size"]
    tolerance = template.config["page_size_tolerance"]
    size_matches = sum(
        abs(width - expected_width) <= tolerance and abs(height - expected_height) <= tolerance
        for width, height in page_sizes
    )
    anchor_matches = sum(anchor.lower() in joined.lower() for anchor in template.config["required_anchors"])
    size_score = size_matches / max(1, len(page_sizes))
    anchor_score = anchor_matches / len(template.config["required_anchors"])
    count_score = 1.0 if len(reader.pages) == template.config["expected_page_count"] else 0.5
    confidence = round(0.35 * size_score + 0.55 * anchor_score + 0.10 * count_score, 4)
    matched = confidence >= 0.75

    return DocumentManifest(
        source_path=str(source),
        filename=source.name,
        sha256=sha256_file(source),
        file_size_bytes=source.stat().st_size,
        page_count=len(reader.pages),
        page_sizes=page_sizes,
        encrypted=bool(reader.is_encrypted),
        pdf_version=getattr(reader, "pdf_header", None),
        metadata=_json_metadata(reader.metadata),
        template_key=template.key if matched else None,
        template_version=template.version if matched else None,
        template_confidence=confidence,
        **_cover_fields(texts[0] if texts else ""),
    )
