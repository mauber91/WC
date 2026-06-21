from __future__ import annotations

import re
import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable

from world_cup_api.domain.name_match import normalize_name
from world_cup_api.pipelines.fifa_pmsr.types import (
    EventRecord,
    IssueRecord,
    NetworkEdgeRecord,
    ObservationRecord,
    ParticipantRecord,
    RawPage,
)
from world_cup_api.pipelines.fifa_pmsr.ocr import ocr_numeric_bbox


PUA_DIGIT_MAP = {
    "\ue071": "0",
    "\ue072": "1",
    "\ue073": "2",
    "\ue074": "3",
    "\ue075": "4",
    "\ue076": "5",
    "\ue077": "6",
    "\ue078": "7",
    "\ue079": "8",
    "\ue07a": "9",
    "\ue094": ".",
}


PHYSICAL_METRICS = [
    ("physical.total_distance", "m"),
    ("physical.zone_1_distance", "m"),
    ("physical.zone_2_distance", "m"),
    ("physical.zone_3_distance", "m"),
    ("physical.zone_4_distance", "m"),
    ("physical.zone_5_distance", "m"),
    ("physical.high_speed_runs", "count"),
    ("physical.sprints", "count"),
    ("physical.top_speed", "km/h"),
]


@dataclass
class CoreExtraction:
    participants: list[ParticipantRecord] = field(default_factory=list)
    observations: list[ObservationRecord] = field(default_factory=list)
    events: list[EventRecord] = field(default_factory=list)
    network_edges: list[NetworkEdgeRecord] = field(default_factory=list)
    issues: list[IssueRecord] = field(default_factory=list)
    attempt_details: dict[tuple[str, int], dict[str, Any]] = field(default_factory=dict)


def decode_pua_number(value: str) -> float | None:
    decoded = "".join(PUA_DIGIT_MAP.get(character, character) for character in value).strip()
    decoded = decoded.replace(",", "").replace("%", "")
    if not re.fullmatch(r"[-+]?\d+(?:\.\d+)?", decoded):
        return None
    return float(decoded)


def _words(page: RawPage) -> list[dict[str, Any]]:
    return page.payloads.get("text_spans", [])


def _line_groups(words: Iterable[dict[str, Any]], tolerance: float = 1.0) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    for word in sorted(words, key=lambda item: (float((item.get("bbox") or [0, 0])[1]), float((item.get("bbox") or [0])[0]))):
        top = float((word.get("bbox") or [0, 0])[1])
        if groups:
            previous_top = float((groups[-1][0].get("bbox") or [0, 0])[1])
            if abs(top - previous_top) <= tolerance:
                groups[-1].append(word)
                continue
        groups.append([word])
    for group in groups:
        group.sort(key=lambda item: float((item.get("bbox") or [0])[0]))
    return groups


def _union_bbox(words: list[dict[str, Any]]) -> list[float] | None:
    boxes: list[list[float]] = [list(word["bbox"]) for word in words if word.get("bbox")]
    if not boxes:
        return None
    return [
        min(float(box[0]) for box in boxes),
        min(float(box[1]) for box in boxes),
        max(float(box[2]) for box in boxes),
        max(float(box[3]) for box in boxes),
    ]


def _parse_minute(value: str) -> tuple[int, int | None] | None:
    match = re.fullmatch(r"(\d{1,3})(?:\+(\d{1,2}))?'", value)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)) if match.group(2) else None


def _participant_from_side(
    page_number: int,
    team: str,
    row: list[dict[str, Any]],
    side: str,
    is_starter: bool,
) -> tuple[ParticipantRecord | None, list[EventRecord]]:
    tokens = [str(item.get("text", "")) for item in row]
    text = " ".join(tokens)
    minute_tokens = [token for token in tokens if _parse_minute(token)]
    if side == "left":
        match = re.match(r"^(\d{1,2})\s+(GK|DF|MF|FW)\s*(.+)$", text)
        if not match:
            match = re.match(r"^(\d{1,2})\s+(GK|DF|MF|FW)([A-Z].+)$", text)
        if not match:
            return None, []
        number, position, remainder = match.groups()
        name_tokens = [token for token in remainder.split() if not _parse_minute(token)]
        name = " ".join(name_tokens)
    else:
        text_without_minutes = " ".join(token for token in tokens if not _parse_minute(token))
        match = re.match(r"^(.+?)\s+(GK|DF|MF|FW)\s*(\d{1,2})$", text_without_minutes)
        if not match:
            return None, []
        name, position, number = match.groups()
    name = re.sub(r"\s+", " ", name).strip()
    if not name or len(name) > 80:
        return None, []
    ids = [str(item["id"]) for item in row]
    participant = ParticipantRecord(
        page_number=page_number,
        team_source_name=team,
        source_name=name,
        normalized_name=normalize_name(name),
        shirt_number=int(number),
        position=position,
        is_starter=is_starter,
        is_substitute=not is_starter,
        source_bbox=_union_bbox(row),
        source_element_ids=ids,
        method="positioned_text",
        confidence=0.98,
    )
    events: list[EventRecord] = []
    for token in minute_tokens:
        minute, added = _parse_minute(token) or (None, None)
        events.append(
            EventRecord(
                page_number=page_number,
                event_type="lineup_annotation",
                team_source_name=team,
                participant_name=name,
                minute=minute,
                added_time=added,
                match_second=(minute * 60 + (added or 0) * 60) if minute is not None else None,
                attributes={"raw_marker": token, "is_starter": is_starter},
                source_bbox=_union_bbox(row),
                source_element_ids=ids,
                method="positioned_text",
                confidence=0.82,
            )
        )
    return participant, events


def _extract_participants(page: RawPage, result: CoreExtraction) -> None:
    substitute_top = 10_000.0
    for word in _words(page):
        if str(word.get("text", "")).upper() == "SUBSTITUTES":
            substitute_top = min(substitute_top, float((word.get("bbox") or [0, 0])[1]))

    for row in _line_groups(_words(page)):
        top = float((row[0].get("bbox") or [0, 0])[1])
        if not 120 <= top <= 510:
            continue
        left = [word for word in row if float((word.get("bbox") or [0])[0]) < 315]
        right = [word for word in row if float((word.get("bbox") or [0])[0]) > 700]
        for team, side, side_words in (("Brazil", "left", left), ("Haiti", "right", right)):
            if not side_words:
                continue
            participant, events = _participant_from_side(
                page.page_number, team, side_words, side, top < substitute_top
            )
            if participant and not any(
                existing.team_source_name == participant.team_source_name
                and existing.shirt_number == participant.shirt_number
                for existing in result.participants
            ):
                result.participants.append(participant)
                result.events.extend(events)


def _metric_key(label: str) -> str:
    normalized = label.lower().replace("%", " percent ")
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    return f"summary.{normalized}"


def _parse_number(value: str) -> float | None:
    match = re.search(r"-?\d+(?:\.\d+)?", value.replace(",", ""))
    return float(match.group()) if match else None


def _extract_key_statistics(page: RawPage, result: CoreExtraction) -> None:
    lines = [line.strip() for line in page.raw_text.splitlines() if line.strip()]
    possession = re.search(
        r"Total\s+(\d+(?:\.\d+)?)%\s+(\d+(?:\.\d+)?)%\s+(\d+(?:\.\d+)?)%\s+Total",
        page.raw_text,
        flags=re.IGNORECASE,
    )
    if possession:
        for team, value in (("Brazil", possession.group(1)), ("Haiti", possession.group(3))):
            result.observations.append(
                ObservationRecord(
                    page_number=page.page_number,
                    scope="team",
                    team_source_name=team,
                    metric_key="summary.possession",
                    value_numeric=float(value),
                    unit="%",
                    method="layout_text",
                    confidence=0.995,
                )
            )
        result.observations.append(
            ObservationRecord(
                page_number=page.page_number,
                scope="match",
                metric_key="summary.possession_in_contest",
                value_numeric=float(possession.group(2)),
                unit="%",
                method="layout_text",
                confidence=0.995,
            )
        )
    for line in lines:
        match = re.match(r"^(.+?)\s{3,}([A-Za-z].*?)\s{3,}(.+?)$", line)
        if not match:
            continue
        left, label, right = (part.strip() for part in match.groups())
        if not any(character.isdigit() for character in left + right):
            continue
        unit = "%" if "%" in left or "%" in right else "km" if "km" in left or "km" in right else None
        for team, raw_value in (("Brazil", left), ("Haiti", right)):
            numeric = _parse_number(raw_value)
            result.observations.append(
                ObservationRecord(
                    page_number=page.page_number,
                    scope="team",
                    team_source_name=team,
                    metric_key=_metric_key(label),
                    value_numeric=numeric,
                    value_text=raw_value,
                    unit=unit,
                    is_explicit_zero=numeric == 0,
                    dimensions={"source_label": label},
                    method="layout_text",
                    confidence=0.99,
                )
            )
            parenthesized = re.search(r"\((\d+(?:\.\d+)?)\)", raw_value)
            if parenthesized:
                result.observations.append(
                    ObservationRecord(
                        page_number=page.page_number,
                        scope="team",
                        team_source_name=team,
                        metric_key=f"{_metric_key(label)}.parenthesized",
                        value_numeric=float(parenthesized.group(1)),
                        dimensions={"source_label": label},
                        method="layout_text",
                        confidence=0.99,
                    )
                )


def _extract_table_cells(page: RawPage, result: CoreExtraction) -> None:
    for cell in page.payloads.get("table_cells", []):
        value = cell.get("text")
        result.observations.append(
            ObservationRecord(
                page_number=page.page_number,
                scope="table_cell",
                metric_key="table.cell",
                value_text=None if value is None else str(value),
                is_blank=value is None or str(value).strip() == "",
                dimensions={
                    "page_type": page.classification.page_type,
                    "table_index": cell.get("table_index"),
                    "row_index": cell.get("row_index"),
                    "column_index": cell.get("column_index"),
                },
                source_bbox=cell.get("bbox"),
                source_element_ids=[str(cell["id"])],
                method="pdf_table_geometry",
                confidence=0.92,
            )
        )


def _extract_physical(page: RawPage, result: CoreExtraction) -> None:
    words = _words(page)
    rows = _line_groups(words, tolerance=1.2)
    for row in rows:
        pua_words = [word for word in row if any(character in PUA_DIGIT_MAP for character in str(word.get("text", "")))]
        if not pua_words:
            continue
        left_words = [word for word in row if float((word.get("bbox") or [0])[0]) < 270]
        if not left_words:
            continue
        tokens = [str(word.get("text", "")) for word in left_words]
        if not tokens[0].isdigit():
            continue
        player_name = " ".join(tokens[1:]).strip()
        if not player_name:
            continue
        for word in pua_words:
            x0 = float((word.get("bbox") or [0])[0])
            column = min(range(len(PHYSICAL_METRICS)), key=lambda index: abs(x0 - [284, 364, 443, 527, 619, 697, 778, 850, 922][index]))
            value = decode_pua_number(str(word.get("text", "")))
            method = "font_glyph_map"
            confidence = 0.995
            if value is None and word.get("bbox"):
                value, confidence = ocr_numeric_bbox(
                    page.render_uri,
                    word["bbox"],
                    page.width_points,
                    page.height_points,
                )
                method = "targeted_tesseract_ocr"
            metric_key, unit = PHYSICAL_METRICS[column]
            if value is None:
                result.issues.append(
                    IssueRecord(
                        page_number=page.page_number,
                        severity="warning",
                        code="physical_glyph_unmapped",
                        message=f"Could not decode physical value for {player_name}",
                        artifact_type="glyph",
                        source_bbox=word.get("bbox"),
                        source_element_ids=[str(word["id"])],
                        evidence={"raw_text": word.get("text")},
                    )
                )
                continue
            result.observations.append(
                ObservationRecord(
                    page_number=page.page_number,
                    scope="player",
                    team_source_name=page.classification.team_scope,
                    participant_name=player_name,
                    metric_key=metric_key,
                    value_numeric=value,
                    unit=unit,
                    is_explicit_zero=value == 0,
                    source_bbox=word.get("bbox"),
                    source_element_ids=[str(word["id"])],
                    dimensions={
                        "font_name": word.get("fontname"),
                        "font_checksum": hashlib.sha256(
                            str(word.get("fontname") or "unknown-font").encode("utf-8")
                        ).hexdigest(),
                    },
                    method=method,
                    confidence=confidence,
                )
            )


def _cluster_centers(values: list[float], tolerance: float = 5.0) -> list[float]:
    clusters: list[list[float]] = []
    for value in sorted(values):
        if clusters and abs(value - sum(clusters[-1]) / len(clusters[-1])) <= tolerance:
            clusters[-1].append(value)
        else:
            clusters.append([value])
    return [sum(cluster) / len(cluster) for cluster in clusters]


def _extract_network(page: RawPage, result: CoreExtraction) -> None:
    words = _words(page)
    candidate_rows: list[tuple[float, str, list[dict[str, Any]]]] = []
    numeric_centers: list[float] = []
    for row in _line_groups(words, tolerance=1.0):
        top = float((row[0].get("bbox") or [0, 0])[1])
        if not 118 <= top <= 515:
            continue
        left = [word for word in row if float((word.get("bbox") or [0])[0]) < 150]
        if not left or not str(left[0].get("text", "")).isdigit():
            continue
        player_name = " ".join(str(word.get("text", "")) for word in left[1:]).strip()
        if not player_name:
            continue
        matrix_words = [
            word
            for word in row
            if 150 <= float((word.get("bbox") or [0])[0]) <= 745
            and str(word.get("text", "")).isdigit()
        ]
        candidate_rows.append((top, player_name, matrix_words))
        numeric_centers.extend(
            (float(word["bbox"][0]) + float(word["bbox"][2])) / 2 for word in matrix_words
        )
    players = [name for _, name, _ in candidate_rows]
    centers = _cluster_centers(numeric_centers)
    if len(players) < 5 or len(centers) < len(players) - 2:
        result.issues.append(
            IssueRecord(
                page_number=page.page_number,
                severity="warning",
                code="network_matrix_alignment",
                message="Passing matrix grid could not be aligned confidently",
                artifact_type="table",
                evidence={"players": len(players), "columns": len(centers)},
            )
        )
        return
    centers = centers[: len(players)]
    pending: list[NetworkEdgeRecord] = []
    for _, source, matrix_words in candidate_rows:
        for word in matrix_words:
            center = (float(word["bbox"][0]) + float(word["bbox"][2])) / 2
            target_index = min(range(len(centers)), key=lambda index: abs(center - centers[index]))
            if target_index >= len(players):
                continue
            count = int(str(word.get("text", "0")))
            if count <= 0 or source == players[target_index]:
                continue
            pending.append(
                NetworkEdgeRecord(
                    page_number=page.page_number,
                    team_source_name=page.classification.team_scope or "",
                    source_player_name=source,
                    target_player_name=players[target_index],
                    pass_count=count,
                    source_bbox=word.get("bbox"),
                    source_element_ids=[str(word["id"])],
                    method="positioned_matrix",
                    confidence=0.97,
                )
            )
    total = sum(edge.pass_count for edge in pending)
    for edge in pending:
        edge.pass_share = edge.pass_count / total if total else None
    result.network_edges.extend(pending)


ATTEMPT_OUTCOMES = [
    "Goal",
    "On Target - Saved",
    "Deflected Off Target - Defensive Event",
    "Off Target",
    "Blocked",
    "Incomplete",
]
BODY_PARTS = ["Right Foot", "Left Foot", "Head", "Other"]


def _extract_attempt_table(page: RawPage, result: CoreExtraction) -> None:
    event_number = 0
    for line in page.raw_text.splitlines():
        stripped = line.strip()
        match = re.match(r"^(\d{1,3})(?:\+(\d{1,2}))?\s+(.+)$", stripped)
        if not match:
            continue
        remainder = match.group(3)
        outcome = next((candidate for candidate in ATTEMPT_OUTCOMES if candidate in remainder), None)
        if outcome is None:
            continue
        event_number += 1
        player = remainder.split(outcome, 1)[0].strip()
        body_part = next((candidate for candidate in BODY_PARTS if candidate in remainder), None)
        minute = int(match.group(1))
        added = int(match.group(2)) if match.group(2) else None
        details = {
            "participant_name": player,
            "outcome": outcome,
            "body_part": body_part,
            "minute": minute,
            "added_time": added,
            "raw_row": stripped,
        }
        team = page.classification.team_scope or ""
        result.attempt_details[(team, event_number)] = details
        result.events.append(
            EventRecord(
                page_number=page.page_number,
                event_type="attempt",
                event_number=event_number,
                team_source_name=team,
                participant_name=player,
                minute=minute,
                added_time=added,
                match_second=(minute + (added or 0)) * 60,
                outcome=outcome,
                body_part=body_part,
                attributes={"raw_row": stripped},
                method="layout_table",
                confidence=0.96,
            )
        )


def _promote_substitutions(result: CoreExtraction) -> None:
    grouped: dict[tuple[str, int, int | None], list[EventRecord]] = defaultdict(list)
    for event in result.events:
        if event.event_type == "lineup_annotation" and event.minute is not None:
            grouped[(event.team_source_name or "", event.minute, event.added_time)].append(event)
    for (team, minute, added), events in grouped.items():
        outgoing = [event for event in events if event.attributes.get("is_starter")]
        incoming = [event for event in events if not event.attributes.get("is_starter")]
        for out_event, in_event in zip(outgoing, incoming, strict=False):
            result.events.append(
                EventRecord(
                    page_number=out_event.page_number,
                    event_type="substitution",
                    team_source_name=team,
                    participant_name=in_event.participant_name,
                    minute=minute,
                    added_time=added,
                    match_second=(minute + (added or 0)) * 60,
                    outcome="completed",
                    attributes={
                        "player_out": out_event.participant_name,
                        "player_in": in_event.participant_name,
                    },
                    source_element_ids=out_event.source_element_ids + in_event.source_element_ids,
                    method="paired_lineup_markers",
                    confidence=0.88,
                )
            )


def _extract_meter_labels(page: RawPage, result: CoreExtraction) -> None:
    if page.classification.page_type not in {"line_height", "defensive_line_height"}:
        return
    for word in _words(page):
        match = re.fullmatch(r"(\d+(?:\.\d+)?)m", str(word.get("text", "")), flags=re.IGNORECASE)
        if not match:
            continue
        value = float(match.group(1))
        result.observations.append(
            ObservationRecord(
                page_number=page.page_number,
                scope="team",
                team_source_name=page.classification.team_scope,
                metric_key="spatial.line_or_team_length",
                value_numeric=value,
                unit="m",
                dimensions={"page_type": page.classification.page_type},
                source_bbox=word.get("bbox"),
                source_element_ids=[str(word["id"])],
                method="visual_label",
                confidence=0.98,
            )
        )


def extract_core_semantics(pages: list[RawPage]) -> CoreExtraction:
    result = CoreExtraction()
    for page in pages:
        _extract_table_cells(page, result)
        page_type = page.classification.page_type
        if page_type == "match_summary_teams":
            _extract_participants(page, result)
        elif page_type == "key_statistics":
            _extract_key_statistics(page, result)
        elif page_type == "physical_data":
            _extract_physical(page, result)
        elif page_type == "passing_network":
            _extract_network(page, result)
        elif page_type == "attempts_table":
            _extract_attempt_table(page, result)
        _extract_meter_labels(page, result)
    _promote_substitutions(result)
    if len(result.participants) < 44:
        result.issues.append(
            IssueRecord(
                page_number=2,
                severity="warning",
                code="participant_coverage",
                message=f"Only {len(result.participants)} report participants were parsed",
                artifact_type="text",
            )
        )
    return result
