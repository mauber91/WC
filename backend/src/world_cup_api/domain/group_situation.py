from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

import numpy as np

from world_cup_api.domain.standings import MatchRecord, StandingRow, calculate_group_table
from world_cup_api.modeling.prediction import one_x_two, reweight_score_matrix


@dataclass(frozen=True)
class Md3Fixture:
    team_a_id: int
    team_b_id: int


@dataclass(frozen=True)
class TeamGroupSituation:
    team_id: int
    min_position: int
    max_position: int
    reachable_positions: frozenset[int]
    position_locked: bool
    locked_position: int | None
    can_qualify_top_two: bool
    can_miss_top_two: bool
    qualifies_with_win: bool
    qualifies_with_draw: bool
    qualifies_with_loss: bool
    eliminated_with_loss: bool


@dataclass(frozen=True)
class GroupSituation:
    fixtures: tuple[Md3Fixture, Md3Fixture]
    teams: tuple[TeamGroupSituation, ...]

    def by_team_id(self) -> dict[int, TeamGroupSituation]:
        return {team.team_id: team for team in self.teams}


# Representative scorelines for each result type.
_WIN_SCORELINES = ((1, 0), (2, 0), (3, 0), (4, 0), (5, 0))
_DRAW_SCORELINES = ((0, 0), (1, 1), (2, 2), (3, 3))
_LOSS_SCORELINES = ((0, 1), (0, 2), (0, 3), (0, 4), (0, 5))
_ALL_SCORELINES = _WIN_SCORELINES + _DRAW_SCORELINES + _LOSS_SCORELINES
_CORE_SCORELINES = (_WIN_SCORELINES[0], _DRAW_SCORELINES[0], _LOSS_SCORELINES[0])


def md3_fixtures_from_matches(matches: Iterable[dict]) -> tuple[Md3Fixture, Md3Fixture]:
    late = [match for match in matches if int(match["matchday"]) == 3]
    if len(late) != 2:
        raise ValueError(f"Expected exactly two matchday-3 fixtures, found {len(late)}")
    ordered = sorted(late, key=lambda item: (item.get("scheduled_at"), item["id"]))
    return (
        Md3Fixture(team_a_id=int(ordered[0]["a"]), team_b_id=int(ordered[0]["b"])),
        Md3Fixture(team_a_id=int(ordered[1]["a"]), team_b_id=int(ordered[1]["b"])),
    )


def analyze_group_before_matchday3(
    teams: Iterable[StandingRow],
    early_records: Iterable[MatchRecord],
    md3_fixtures: tuple[Md3Fixture, Md3Fixture],
    *,
    detailed_scorelines: bool = False,
) -> GroupSituation:
    """Enumerate joint matchday-3 outcomes and derive each team's reachable table positions."""
    scorelines = _ALL_SCORELINES if detailed_scorelines else _CORE_SCORELINES
    team_rows = [
        StandingRow(
            team_id=row.team_id,
            name=row.name,
            fifa_rank_history=tuple(row.fifa_rank_history),
            conduct_score=row.conduct_score,
        )
        for row in teams
    ]
    team_ids = {row.team_id for row in team_rows}
    if len(team_ids) != 4:
        raise ValueError("Group situation analysis requires exactly four teams")

    base_records = list(early_records)
    fixture_a, fixture_b = md3_fixtures
    _validate_fixture(fixture_a, team_ids)
    _validate_fixture(fixture_b, team_ids)

    reachable: dict[int, set[int]] = {team_id: set() for team_id in team_ids}
    top_two_with: dict[int, set[str]] = {team_id: set() for team_id in team_ids}
    loss_positions: dict[int, list[int]] = {team_id: [] for team_id in team_ids}

    for scoreline_a in scorelines:
        for scoreline_b in scorelines:
            records = base_records + [
                MatchRecord(fixture_a.team_a_id, fixture_a.team_b_id, scoreline_a[0], scoreline_a[1]),
                MatchRecord(fixture_b.team_a_id, fixture_b.team_b_id, scoreline_b[0], scoreline_b[1]),
            ]
            table = calculate_group_table(_fresh_rows(team_rows), records).rows
            positions = {row.team_id: row.position for row in table}
            for team_id, position in positions.items():
                reachable[team_id].add(position)

            for team_id in team_ids:
                own_fixture, own_scoreline = _team_fixture_and_scoreline(
                    team_id, fixture_a, fixture_b, scoreline_a, scoreline_b,
                )
                if own_fixture is None:
                    continue
                result = _result_for_team(team_id, own_fixture, own_scoreline)
                if positions[team_id] <= 2:
                    top_two_with[team_id].add(result)
                if result == "loss":
                    loss_positions[team_id].append(positions[team_id])

    team_situations = tuple(
        _build_team_situation(team_id, reachable[team_id], top_two_with[team_id], loss_positions[team_id])
        for team_id in sorted(team_ids)
    )
    return GroupSituation(fixtures=md3_fixtures, teams=team_situations)


def _fresh_rows(team_rows: list[StandingRow]) -> list[StandingRow]:
    return [
        StandingRow(
            team_id=row.team_id,
            name=row.name,
            fifa_rank_history=tuple(row.fifa_rank_history),
            conduct_score=row.conduct_score,
        )
        for row in team_rows
    ]


def _validate_fixture(fixture: Md3Fixture, team_ids: set[int]) -> None:
    if fixture.team_a_id not in team_ids or fixture.team_b_id not in team_ids:
        raise ValueError("Matchday-3 fixture includes a team outside the group")
    if fixture.team_a_id == fixture.team_b_id:
        raise ValueError("Matchday-3 fixture teams must differ")


def _team_fixture_and_scoreline(
    team_id: int,
    fixture_a: Md3Fixture,
    fixture_b: Md3Fixture,
    scoreline_a: tuple[int, int],
    scoreline_b: tuple[int, int],
) -> tuple[Md3Fixture | None, tuple[int, int] | None]:
    if team_id in (fixture_a.team_a_id, fixture_a.team_b_id):
        return fixture_a, scoreline_a
    if team_id in (fixture_b.team_a_id, fixture_b.team_b_id):
        return fixture_b, scoreline_b
    return None, None


def _result_for_team(team_id: int, fixture: Md3Fixture, scoreline: tuple[int, int]) -> str:
    goals_a, goals_b = scoreline
    if team_id == fixture.team_a_id:
        if goals_a > goals_b:
            return "win"
        if goals_a < goals_b:
            return "loss"
        return "draw"
    if goals_a > goals_b:
        return "loss"
    if goals_a < goals_b:
        return "win"
    return "draw"


def _build_team_situation(
    team_id: int,
    reachable: set[int],
    top_two_with: set[str],
    loss_positions: list[int],
) -> TeamGroupSituation:
    min_position = min(reachable)
    max_position = max(reachable)
    position_locked = len(reachable) == 1
    locked_position = min_position if position_locked else None
    return TeamGroupSituation(
        team_id=team_id,
        min_position=min_position,
        max_position=max_position,
        reachable_positions=frozenset(reachable),
        position_locked=position_locked,
        locked_position=locked_position,
        can_qualify_top_two=min_position <= 2,
        can_miss_top_two=max_position > 2,
        qualifies_with_win="win" in top_two_with,
        qualifies_with_draw="draw" in top_two_with,
        qualifies_with_loss="loss" in top_two_with,
        eliminated_with_loss=bool(loss_positions) and all(position > 2 for position in loss_positions),
    )


def rotation_elo_penalty(
    situation: TeamGroupSituation,
    params: Mapping[str, float | int],
) -> float:
    locked_first = float(params["rotation_elo_locked_first"])
    clinched = float(params["rotation_elo_clinched"])
    eliminated = float(params["rotation_elo_eliminated"])

    if situation.position_locked:
        if situation.locked_position == 1:
            return locked_first
        if situation.locked_position == 2:
            return clinched
        return eliminated

    if not situation.can_qualify_top_two:
        return eliminated
    if not situation.can_miss_top_two and situation.min_position >= 2:
        return clinched
    if situation.min_position == 1:
        return 0.0
    return 0.0


def should_rotate_team(
    situation: TeamGroupSituation,
    params: Mapping[str, float | int],
) -> bool:
    return rotation_elo_penalty(situation, params) > 0.0


def mutual_draw_incentive(
    situation_a: TeamGroupSituation,
    situation_b: TeamGroupSituation,
) -> bool:
    """Both teams advance with a draw and are knocked out of the top two on any loss."""
    return (
        situation_a.qualifies_with_draw
        and situation_b.qualifies_with_draw
        and situation_a.eliminated_with_loss
        and situation_b.eliminated_with_loss
    )


def apply_collusion_draw_boost(matrix: np.ndarray, boost: float) -> np.ndarray:
    if boost <= 0:
        return matrix
    win, draw, loss = one_x_two(matrix)
    target_draw = min(draw + boost, 0.85)
    remainder = max(1.0 - target_draw, 0.0)
    if remainder <= 0:
        return matrix
    scale = remainder / max(win + loss, 1e-12)
    return reweight_score_matrix(matrix, (win * scale, target_draw, loss * scale))
