from __future__ import annotations

from dataclasses import dataclass, field
from math import hypot
from typing import Any

from world_cup_api.pipelines.fifa_pmsr.coordinates import PitchTransform, normalize_goal_mouth_point
from world_cup_api.pipelines.fifa_pmsr.types import (
    EventRecord,
    IssueRecord,
    RawPage,
    ParticipantRecord,
    SpatialFeatureRecord,
    TimeseriesPointRecord,
)


@dataclass
class VisualExtraction:
    events: list[EventRecord] = field(default_factory=list)
    spatial_features: list[SpatialFeatureRecord] = field(default_factory=list)
    timeseries_points: list[TimeseriesPointRecord] = field(default_factory=list)
    issues: list[IssueRecord] = field(default_factory=list)


COLOR_CATEGORIES = {
    (0.1804, 0.302, 1.0): "complete",
    (0.9608, 0.7373, 0.0): "incomplete_or_off_target",
    (1.0, 0.0, 0.0): "incomplete",
    (0.0, 0.502, 0.0): "goal",
    (0.3569, 0.6078, 0.8353): "on_target",
    (0.702, 0.5333, 1.0): "blocked",
    (1.0, 0.2392, 0.0): "pressure_or_regain",
}


MARKER_REGIONS: dict[str, list[tuple[float, float, float, float]]] = {
    "line_breaks_summary": [(30, 145, 610, 480)],
    "offers_to_receive": [(30, 145, 600, 490)],
    "movement_to_receive": [(30, 145, 570, 490)],
    "defensive_actions": [(18, 225, 225, 521), (261, 225, 468, 521)],
    "defensive_pressure": [(18, 127, 269, 484), (692, 127, 942, 484)],
    "goal_prevention": [(30, 145, 610, 490)],
}


ARROW_REGIONS: dict[str, list[tuple[float, float, float, float]]] = {
    "crosses": [(18, 109, 277, 294), (18, 337, 277, 522)],
    "goalkeeper_distribution": [(18, 115, 222, 398), (258, 115, 462, 398), (498, 115, 702, 398)],
    "defensive_pressure": [(18, 127, 269, 484), (692, 127, 942, 484)],
}


def _color(value: Any) -> tuple[float, float, float] | None:
    if not isinstance(value, list | tuple) or len(value) != 3:
        return None
    return tuple(round(float(component), 4) for component in value)


def _category(color: tuple[float, float, float] | None) -> str:
    if color is None:
        return "unknown"
    return min(
        COLOR_CATEGORIES,
        key=lambda candidate: sum((candidate[index] - color[index]) ** 2 for index in range(3)),
    ) and COLOR_CATEGORIES[
        min(
            COLOR_CATEGORIES,
            key=lambda candidate: sum((candidate[index] - color[index]) ** 2 for index in range(3)),
        )
    ]


def _inside(x: float, y: float, bbox: tuple[float, float, float, float]) -> bool:
    return bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3]


def _extract_attempt_map(
    page: RawPage,
    details: dict[tuple[str, int], dict[str, object]],
    result: VisualExtraction,
) -> None:
    words = page.payloads.get("text_spans", [])
    team = page.classification.team_scope or ""
    candidates: dict[int, dict[str, dict[str, object]]] = {}
    for word in words:
        text = str(word.get("text", ""))
        bbox = word.get("bbox")
        if not text.isdigit() or bbox is None or not 1 <= int(text) <= 30:
            continue
        x = (float(bbox[0]) + float(bbox[2])) / 2
        y = (float(bbox[1]) + float(bbox[3])) / 2
        event_number = int(text)
        if 30 <= x <= 410 and 105 <= y <= 330:
            candidates.setdefault(event_number, {})["origin"] = word
        elif 430 <= x <= 730 and 90 <= y <= 270:
            candidates.setdefault(event_number, {})["target"] = word

    pitch = PitchTransform((30, 109, 406, 430), attacking_direction="right")
    goal_bbox = (430.0, 90.0, 730.0, 270.0)
    for event_number, pair in sorted(candidates.items()):
        if "origin" not in pair:
            continue
        origin = pair["origin"]
        obox = origin["bbox"]
        ox = (float(obox[0]) + float(obox[2])) / 2
        oy = (float(obox[1]) + float(obox[3])) / 2
        point = pitch.point(ox, oy)
        target = pair.get("target")
        tx = ty = ntx = nty = None
        ids = [str(origin["id"])]
        if target:
            tbox = target["bbox"]
            tx = (float(tbox[0]) + float(tbox[2])) / 2
            ty = (float(tbox[1]) + float(tbox[3])) / 2
            ntx, nty = normalize_goal_mouth_point(tx, ty, goal_bbox)
            ids.append(str(target["id"]))
        detail = details.get((team, event_number), {})
        result.events.append(
            EventRecord(
                page_number=page.page_number,
                event_type="attempt_spatial",
                event_number=event_number,
                team_source_name=team,
                participant_name=detail.get("participant_name"),
                minute=detail.get("minute"),
                added_time=detail.get("added_time"),
                outcome=detail.get("outcome"),
                body_part=detail.get("body_part"),
                raw_start_x=ox,
                raw_start_y=oy,
                raw_end_x=tx,
                raw_end_y=ty,
                norm_start_x=point["norm_x"],
                norm_start_y=point["norm_y"],
                norm_end_x=ntx,
                norm_end_y=nty,
                pitch_start_x_m=point["pitch_x_m"],
                pitch_start_y_m=point["pitch_y_m"],
                coordinate_space="pitch_to_goal_mouth",
                attacking_direction="right",
                attributes={"target_coordinate_space": "goal_mouth_normalized"},
                source_bbox=[ox, oy, tx or ox, ty or oy],
                source_element_ids=ids,
                method="numbered_map_linkage",
                confidence=0.96 if target else 0.88,
            )
        )


def _extract_markers(page: RawPage, result: VisualExtraction) -> None:
    regions = MARKER_REGIONS.get(page.classification.page_type, [])
    if not regions:
        return
    event_type = {
        "line_breaks_summary": "line_break",
        "offers_to_receive": "offer_to_receive",
        "movement_to_receive": "movement_to_receive",
        "defensive_actions": "defensive_action",
        "defensive_pressure": "pressure",
        "goal_prevention": "goalkeeper_action",
    }[page.classification.page_type]
    seen: set[tuple[int, int, str]] = set()
    for vector in page.payloads.get("vectors", []):
        if vector.get("primitive_type") != "curve" or not vector.get("fill"):
            continue
        width = float(vector.get("width") or 0)
        height = float(vector.get("height") or 0)
        if not (2 <= width <= 14 and 2 <= height <= 14 and abs(width - height) <= 2):
            continue
        x = (float(vector.get("x0") or 0) + float(vector.get("x1") or 0)) / 2
        y = (float(vector.get("top") or 0) + float(vector.get("bottom") or 0)) / 2
        region = next((candidate for candidate in regions if _inside(x, y, candidate)), None)
        if region is None:
            continue
        color = _color(vector.get("non_stroking_color") or vector.get("stroking_color"))
        if color is None or all(component > 0.85 for component in color):
            continue
        category = _category(color)
        key = (round(x), round(y), category)
        if key in seen:
            continue
        seen.add(key)
        transform = PitchTransform(region, attacking_direction="right")
        point = transform.point(x, y)
        result.events.append(
            EventRecord(
                page_number=page.page_number,
                event_type=event_type,
                team_source_name=page.classification.team_scope,
                category=category,
                outcome=category,
                raw_start_x=x,
                raw_start_y=y,
                norm_start_x=point["norm_x"],
                norm_start_y=point["norm_y"],
                pitch_start_x_m=point["pitch_x_m"],
                pitch_start_y_m=point["pitch_y_m"],
                coordinate_space="pitch",
                attacking_direction="right",
                attributes={"color_rgb": color},
                source_bbox=vector.get("bbox"),
                source_element_ids=[str(vector["id"])],
                method="vector_marker",
                confidence=0.88,
            )
        )


def _extract_arrows(page: RawPage, result: VisualExtraction) -> None:
    regions = ARROW_REGIONS.get(page.classification.page_type, [])
    if not regions:
        return
    event_type = {
        "crosses": "cross",
        "goalkeeper_distribution": "goalkeeper_distribution",
        "defensive_pressure": "pressure_vector",
    }[page.classification.page_type]
    seen: set[tuple[int, int, int, int]] = set()
    for vector in page.payloads.get("vectors", []):
        if vector.get("primitive_type") != "line" or not vector.get("stroke"):
            continue
        x0 = float(vector.get("x0") or 0)
        x1 = float(vector.get("x1") or 0)
        y0_pdf = float(vector.get("y0") or 0)
        y1_pdf = float(vector.get("y1") or 0)
        y0 = page.height_points - y0_pdf
        y1 = page.height_points - y1_pdf
        minimum_length = 1.0 if page.classification.page_type == "crosses" else 8.0
        if hypot(x1 - x0, y1 - y0) < minimum_length:
            continue
        midpoint = ((x0 + x1) / 2, (y0 + y1) / 2)
        region = next((candidate for candidate in regions if _inside(*midpoint, candidate)), None)
        if region is None:
            continue
        color = _color(vector.get("stroking_color"))
        if color is None or all(abs(component - color[0]) < 0.02 for component in color):
            continue
        key = (round(x0), round(y0), round(x1), round(y1))
        if key in seen:
            continue
        seen.add(key)
        transform = PitchTransform(region, attacking_direction="right")
        line = transform.line(x0, y0, x1, y1)
        category = _category(color)
        result.events.append(
            EventRecord(
                page_number=page.page_number,
                event_type=event_type,
                team_source_name=page.classification.team_scope,
                category=category,
                outcome=category,
                raw_start_x=x0,
                raw_start_y=y0,
                raw_end_x=x1,
                raw_end_y=y1,
                norm_start_x=line["start_norm_x"],
                norm_start_y=line["start_norm_y"],
                norm_end_x=line["end_norm_x"],
                norm_end_y=line["end_norm_y"],
                pitch_start_x_m=line["start_pitch_x_m"],
                pitch_start_y_m=line["start_pitch_y_m"],
                pitch_end_x_m=line["end_pitch_x_m"],
                pitch_end_y_m=line["end_pitch_y_m"],
                coordinate_space="pitch",
                attacking_direction="right",
                length_m=line["length_m"],
                angle_degrees=line["angle_degrees"],
                attributes={"color_rgb": color, "endpoint_direction_inferred": False},
                source_bbox=vector.get("bbox"),
                source_element_ids=[str(vector["id"])],
                method="vector_line",
                confidence=0.84,
            )
        )


def _extract_line_height_polygons(page: RawPage, result: VisualExtraction) -> None:
    if page.classification.page_type not in {"line_height", "defensive_line_height"}:
        return
    pitch_region = (85.0, 125.0, 875.0, 490.0)
    transform = PitchTransform(pitch_region, attacking_direction="right")
    for vector in page.payloads.get("vectors", []):
        if vector.get("primitive_type") != "rect":
            continue
        x0 = float(vector.get("x0") or 0)
        x1 = float(vector.get("x1") or 0)
        y0 = float(vector.get("top") or 0)
        y1 = float(vector.get("bottom") or 0)
        if not _inside((x0 + x1) / 2, (y0 + y1) / 2, pitch_region):
            continue
        if (x1 - x0) < 8 or (y1 - y0) < 8:
            continue
        corners = [transform.point(x, y) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
        result.spatial_features.append(
            SpatialFeatureRecord(
                page_number=page.page_number,
                feature_type="team_extent",
                geometry_type="polygon",
                coordinate_space="pitch",
                team_source_name=page.classification.team_scope,
                raw_geometry={"type": "Polygon", "coordinates": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]},
                normalized_geometry={
                    "type": "Polygon",
                    "coordinates": [[corner["norm_x"], corner["norm_y"]] for corner in corners],
                },
                canonical_geometry={
                    "type": "Polygon",
                    "coordinates": [[corner["pitch_x_m"], corner["pitch_y_m"]] for corner in corners],
                },
                attributes={
                    "width_m": abs(corners[1]["pitch_x_m"] - corners[0]["pitch_x_m"]),
                    "depth_m": abs(corners[2]["pitch_y_m"] - corners[1]["pitch_y_m"]),
                },
                source_element_ids=[str(vector["id"])],
                method="vector_rectangle",
                confidence=0.82,
            )
        )


def _extract_goalkeeper_timeline(page: RawPage, result: VisualExtraction) -> None:
    if page.classification.page_type != "goalkeeper_involvement":
        return
    charts = [
        ("Brazil", (35.0, 170.0, 755.0, 236.0), 235.0),
        ("Haiti", (35.0, 390.0, 755.0, 456.0), 455.5),
    ]
    seen: set[tuple[str, int]] = set()
    for vector in page.payloads.get("vectors", []):
        if vector.get("primitive_type") != "curve" or not vector.get("fill"):
            continue
        width = float(vector.get("width") or 0)
        height = float(vector.get("height") or 0)
        if not (2.4 <= width <= 3.6 and 2.4 <= height <= 3.6):
            continue
        x = (float(vector.get("x0") or 0) + float(vector.get("x1") or 0)) / 2
        y = (float(vector.get("top") or 0) + float(vector.get("bottom") or 0)) / 2
        for team, bbox, baseline in charts:
            if not _inside(x, y, bbox):
                continue
            minute = max(0, round((x - 35.3) / 7.25))
            value = max(0.0, round((baseline - y) / 20.6, 3))
            key = (team, minute)
            if key in seen:
                continue
            seen.add(key)
            result.timeseries_points.append(
                TimeseriesPointRecord(
                    page_number=page.page_number,
                    series_key="goalkeeper.involvement",
                    team_source_name=team,
                    period="second_half" if minute > 45 else "first_half",
                    minute=minute,
                    match_second=minute * 60,
                    value=value,
                    unit="involvements",
                    raw_x=x,
                    raw_y=y,
                    source_element_ids=[str(vector["id"])],
                    method="vector_chart_calibration",
                    confidence=0.95,
                )
            )


def _extract_formations(
    page: RawPage,
    participants: list[ParticipantRecord],
    result: VisualExtraction,
) -> None:
    if page.classification.page_type != "match_summary_teams":
        return
    pitch_bbox = (338.0, 126.0, 622.0, 332.0)
    participant_lookup = {
        (participant.team_source_name, participant.shirt_number): participant.source_name
        for participant in participants
        if participant.is_starter
    }
    team_points: dict[str, list[tuple[float, float]]] = {"Brazil": [], "Haiti": []}
    for word in page.payloads.get("text_spans", []):
        text = str(word.get("text", ""))
        bbox = word.get("bbox")
        if not text.isdigit() or bbox is None or not 1 <= int(text) <= 26:
            continue
        x = (float(bbox[0]) + float(bbox[2])) / 2
        y = (float(bbox[1]) + float(bbox[3])) / 2
        if not _inside(x, y, pitch_bbox):
            continue
        team = "Brazil" if x < 480 else "Haiti"
        shirt_number = int(text)
        player_name = participant_lookup.get((team, shirt_number))
        if player_name is None:
            continue
        direction = "right" if team == "Brazil" else "left"
        point = PitchTransform(pitch_bbox, attacking_direction=direction).point(x, y)
        normalized_x = point["norm_x"]
        role = (
            "goalkeeper"
            if normalized_x < 0.18
            else "defensive_line"
            if normalized_x < 0.45
            else "midfield_line"
            if normalized_x < 0.72
            else "attacking_line"
        )
        team_points[team].append((point["pitch_x_m"], point["pitch_y_m"]))
        result.spatial_features.append(
            SpatialFeatureRecord(
                page_number=page.page_number,
                feature_type="formation_player",
                geometry_type="point",
                coordinate_space="pitch",
                team_source_name=team,
                participant_name=player_name,
                raw_geometry={"type": "Point", "coordinates": [x, y]},
                normalized_geometry={
                    "type": "Point",
                    "coordinates": [point["norm_x"], point["norm_y"]],
                },
                canonical_geometry={
                    "type": "Point",
                    "coordinates": [point["pitch_x_m"], point["pitch_y_m"]],
                },
                category=role,
                attributes={
                    "shirt_number": shirt_number,
                    "original_attacking_direction": direction,
                    "normalized_attacking_direction": "right",
                },
                source_element_ids=[str(word["id"])],
                method="positioned_formation_label",
                confidence=0.98,
            )
        )
    for team, points in team_points.items():
        if len(points) < 8:
            continue
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        sorted_lines = sorted(set(round(value / 5) * 5 for value in xs))
        spacings = [right - left for left, right in zip(sorted_lines, sorted_lines[1:], strict=False)]
        result.spatial_features.append(
            SpatialFeatureRecord(
                page_number=page.page_number,
                feature_type="formation_summary",
                geometry_type="point",
                coordinate_space="pitch",
                team_source_name=team,
                raw_geometry={"type": "Point", "coordinates": [sum(xs) / len(xs), sum(ys) / len(ys)]},
                normalized_geometry={
                    "type": "Point",
                    "coordinates": [sum(xs) / len(xs) / 105, sum(ys) / len(ys) / 68],
                },
                canonical_geometry={
                    "type": "Point",
                    "coordinates": [sum(xs) / len(xs), sum(ys) / len(ys)],
                },
                attributes={
                    "centroid_x_m": sum(xs) / len(xs),
                    "centroid_y_m": sum(ys) / len(ys),
                    "width_m": max(ys) - min(ys),
                    "depth_m": max(xs) - min(xs),
                    "mean_line_spacing_m": sum(spacings) / len(spacings) if spacings else 0,
                    "player_count": len(points),
                },
                method="derived_formation_geometry",
                confidence=0.95,
            )
        )


def _extract_disciplinary_markers(
    page: RawPage,
    participants: list[ParticipantRecord],
    result: VisualExtraction,
) -> None:
    if page.classification.page_type != "match_summary_teams":
        return
    participant_rows = [participant for participant in participants if participant.source_bbox]
    minute_words = [
        word
        for word in page.payloads.get("text_spans", [])
        if str(word.get("text", "")).rstrip("'").replace("+", "").isdigit()
        and str(word.get("text", "")).endswith("'")
    ]
    for vector in page.payloads.get("vectors", []):
        if vector.get("primitive_type") not in {"rect", "curve"} or not vector.get("fill"):
            continue
        color = _color(vector.get("non_stroking_color"))
        if color is None or not (color[0] > 0.85 and 0.55 < color[1] < 0.9 and color[2] < 0.2):
            continue
        vx = (float(vector.get("x0") or 0) + float(vector.get("x1") or 0)) / 2
        vy = (float(vector.get("top") or 0) + float(vector.get("bottom") or 0)) / 2
        nearest_minute = min(
            minute_words,
            key=lambda word: hypot(
                vx - (float(word["bbox"][0]) + float(word["bbox"][2])) / 2,
                vy - (float(word["bbox"][1]) + float(word["bbox"][3])) / 2,
            ),
            default=None,
        )
        nearest_player = min(
            participant_rows,
            key=lambda participant: abs(
                vy - (float(participant.source_bbox[1]) + float(participant.source_bbox[3])) / 2
            ),
            default=None,
        )
        if nearest_minute is None or nearest_player is None:
            continue
        distance = hypot(
            vx - (float(nearest_minute["bbox"][0]) + float(nearest_minute["bbox"][2])) / 2,
            vy - (float(nearest_minute["bbox"][1]) + float(nearest_minute["bbox"][3])) / 2,
        )
        if distance > 25:
            continue
        raw_minute = str(nearest_minute["text"]).rstrip("'")
        parts = raw_minute.split("+", 1)
        result.events.append(
            EventRecord(
                page_number=page.page_number,
                event_type="card",
                team_source_name=nearest_player.team_source_name,
                participant_name=nearest_player.source_name,
                minute=int(parts[0]),
                added_time=int(parts[1]) if len(parts) == 2 else None,
                category="yellow",
                outcome="shown",
                attributes={"color_rgb": color},
                source_bbox=vector.get("bbox"),
                source_element_ids=[str(vector["id"]), str(nearest_minute["id"])],
                method="vector_marker_nearest_label",
                confidence=0.91,
            )
        )


def extract_visual_semantics(
    pages: list[RawPage],
    attempt_details: dict[tuple[str, int], dict[str, object]],
    participants: list[ParticipantRecord] | None = None,
) -> VisualExtraction:
    result = VisualExtraction()
    participants = participants or []
    for page in pages:
        if page.classification.page_type == "attempts_map":
            _extract_attempt_map(page, attempt_details, result)
        _extract_markers(page, result)
        _extract_arrows(page, result)
        _extract_line_height_polygons(page, result)
        _extract_goalkeeper_timeline(page, result)
        _extract_formations(page, participants, result)
        _extract_disciplinary_markers(page, participants, result)
    return result
