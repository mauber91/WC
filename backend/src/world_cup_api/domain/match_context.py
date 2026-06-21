from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from world_cup_api.domain.bracket import KNOCKOUT_FEEDERS, ROUND_32
from world_cup_api.domain.knockout_fixtures import knockout_schedule, knockout_venue_names
from world_cup_api.domain.venues import travel_km_from_base, venue_point


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def rest_days_between(previous: datetime | None, current: datetime) -> float:
    if previous is None:
        return 0.0
    return max(0.0, (_as_utc(current) - _as_utc(previous)).total_seconds() / 86400.0)


def group_matchday(match_index: int) -> int:
    return match_index // 2 + 1


def group_match_context(
    matches: list[dict[str, Any]],
    team_fifa_by_id: dict[int, str],
) -> dict[int, dict[str, float]]:
    """Compute rest/travel per group match. Travel = base camp -> venue."""
    ordered = sorted(matches, key=lambda item: item["scheduled_at"])
    last_match_at: dict[int, datetime] = {}
    output: dict[int, dict[str, float]] = {}

    for index, match in enumerate(ordered):
        matchday = group_matchday(index)
        team_a = match["a"]
        team_b = match["b"]
        scheduled_at = match["scheduled_at"]
        venue = match["venue"]
        code_a = team_fifa_by_id[team_a]
        code_b = team_fifa_by_id[team_b]

        rest_a = rest_days_between(last_match_at.get(team_a), scheduled_at)
        rest_b = rest_days_between(last_match_at.get(team_b), scheduled_at)
        travel_a = travel_km_from_base(code_a, venue)
        travel_b = travel_km_from_base(code_b, venue)

        if matchday == 1:
            rest_a = rest_b = 0.0

        output[match["id"]] = {
            "matchday": float(matchday),
            "rest_a": rest_a,
            "rest_b": rest_b,
            "travel_a": travel_a,
            "travel_b": travel_b,
        }
        last_match_at[team_a] = scheduled_at
        last_match_at[team_b] = scheduled_at
    return output


def median_matchday3_datetime(group_matches: list[dict[str, Any]]) -> datetime:
    md3 = sorted(
        match["scheduled_at"]
        for index, match in enumerate(sorted(group_matches, key=lambda item: item["scheduled_at"]))
        if group_matchday(index) == 3
    )
    if not md3:
        raise ValueError("No matchday-3 fixtures found")
    return md3[len(md3) // 2]


def knockout_rest_context(
    group_matches_by_code: dict[str, list[dict[str, Any]]],
) -> dict[int, tuple[float, float]]:
    """Precompute rest for each knockout slot side (A/B). Travel is per-trial."""
    from world_cup_api.domain.bracket import ROUND_32

    schedule = knockout_schedule()
    md3_median = median_matchday3_datetime([m for matches in group_matches_by_code.values() for m in matches])

    slot_previous: dict[int, datetime] = {}
    for match_number, sources in ROUND_32.items():
        side_a = _slot_previous_date(sources[0], group_matches_by_code, md3_median)
        side_b = _slot_previous_date(sources[1], group_matches_by_code, md3_median)
        slot_previous[match_number] = (side_a, side_b)

    output: dict[int, tuple[float, float]] = {}
    for match_number, kickoff in sorted(schedule.items()):
        if match_number in slot_previous:
            prev_a, prev_b = slot_previous[match_number]
            output[match_number] = (
                rest_days_between(prev_a, kickoff),
                rest_days_between(prev_b, kickoff),
            )
            continue

        feeders = KNOCKOUT_FEEDERS.get(match_number)
        if feeders is None:
            continue
        prev_a = schedule[feeders[0]]
        prev_b = schedule[feeders[1]]
        output[match_number] = (
            rest_days_between(prev_a, kickoff),
            rest_days_between(prev_b, kickoff),
        )
    return output


def knockout_venue_coords() -> dict[int, tuple[float, float]]:
    names = knockout_venue_names()
    return {match_number: (venue_point(name).lat, venue_point(name).lon) for match_number, name in names.items()}


def travel_km_for_team(base_camp: tuple[float, float], venue_coords: tuple[float, float]) -> float:
    from world_cup_api.domain.venues import GeoPoint, haversine_km

    return haversine_km(GeoPoint(*base_camp), GeoPoint(*venue_coords))


def _slot_previous_date(
    source: tuple[str, str],
    group_matches_by_code: dict[str, list[dict[str, Any]]],
    md3_median: datetime,
) -> datetime:
    kind, reference = source
    if kind == "third":
        return md3_median
    ordered = sorted(group_matches_by_code[reference], key=lambda item: item["scheduled_at"])
    md3 = [match["scheduled_at"] for index, match in enumerate(ordered) if group_matchday(index) == 3]
    return md3[0] if md3 else md3_median
