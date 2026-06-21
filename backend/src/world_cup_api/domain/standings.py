from __future__ import annotations

from dataclasses import dataclass, field
from itertools import groupby
from typing import Callable, Iterable


class UnresolvedTieError(ValueError):
    """Raised when official inputs cannot resolve a FIFA table tie."""


@dataclass(frozen=True)
class MatchRecord:
    team_a_id: int
    team_b_id: int
    goals_a: int
    goals_b: int
    conduct_a: int | None = None
    conduct_b: int | None = None


@dataclass
class StandingRow:
    team_id: int
    name: str = ""
    played: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0
    goals_for: int = 0
    goals_against: int = 0
    points: int = 0
    conduct_score: int | None = 0
    fifa_rank_history: tuple[int, ...] = field(default_factory=tuple)
    position: int = 0

    @property
    def goal_difference(self) -> int:
        return self.goals_for - self.goals_against


@dataclass(frozen=True)
class RankedTable:
    rows: list[StandingRow]
    provisional: bool
    warnings: tuple[str, ...]


def calculate_group_table(
    teams: Iterable[StandingRow], matches: Iterable[MatchRecord]
) -> RankedTable:
    rows = {row.team_id: row for row in teams}
    match_list = list(matches)
    for match in match_list:
        a = rows[match.team_a_id]
        b = rows[match.team_b_id]
        a.played += 1
        b.played += 1
        a.goals_for += match.goals_a
        a.goals_against += match.goals_b
        b.goals_for += match.goals_b
        b.goals_against += match.goals_a
        if match.goals_a > match.goals_b:
            a.won += 1
            b.lost += 1
            a.points += 3
        elif match.goals_a < match.goals_b:
            b.won += 1
            a.lost += 1
            b.points += 3
        else:
            a.drawn += 1
            b.drawn += 1
            a.points += 1
            b.points += 1
        a.conduct_score = _add_conduct(a.conduct_score, match.conduct_a)
        b.conduct_score = _add_conduct(b.conduct_score, match.conduct_b)

    warnings: list[str] = []
    ordered: list[StandingRow] = []
    by_points = sorted(rows.values(), key=lambda row: row.points, reverse=True)
    for _, tied_iter in groupby(by_points, key=lambda row: row.points):
        tied = list(tied_iter)
        if len(tied) == 1:
            ordered.extend(tied)
            continue
        partitions = _resolve_head_to_head([row.team_id for row in tied], match_list)
        for partition in partitions:
            subset = [rows[team_id] for team_id in partition]
            ordered.extend(_resolve_overall(subset, warnings))

    for index, row in enumerate(ordered, start=1):
        row.position = index
    return RankedTable(ordered, bool(warnings), tuple(dict.fromkeys(warnings)))


def rank_third_place(rows: Iterable[StandingRow]) -> RankedTable:
    warnings: list[str] = []
    ordered = _partition_sort(
        list(rows),
        [
            lambda row: row.points,
            lambda row: row.goal_difference,
            lambda row: row.goals_for,
        ],
    )
    resolved: list[StandingRow] = []
    for partition in ordered:
        resolved.extend(_resolve_conduct_then_rank(partition, warnings))
    for index, row in enumerate(resolved, start=1):
        row.position = index
    return RankedTable(resolved, bool(warnings), tuple(dict.fromkeys(warnings)))


def _add_conduct(current: int | None, value: int | None) -> int | None:
    if current is None or value is None:
        return None
    return current + value


def _resolve_head_to_head(team_ids: list[int], matches: list[MatchRecord]) -> list[list[int]]:
    if len(team_ids) == 1:
        return [team_ids]
    candidate_set = set(team_ids)
    stats = {team_id: [0, 0, 0] for team_id in team_ids}  # points, GD, GF
    for match in matches:
        if match.team_a_id not in candidate_set or match.team_b_id not in candidate_set:
            continue
        stats[match.team_a_id][1] += match.goals_a - match.goals_b
        stats[match.team_a_id][2] += match.goals_a
        stats[match.team_b_id][1] += match.goals_b - match.goals_a
        stats[match.team_b_id][2] += match.goals_b
        if match.goals_a > match.goals_b:
            stats[match.team_a_id][0] += 3
        elif match.goals_b > match.goals_a:
            stats[match.team_b_id][0] += 3
        else:
            stats[match.team_a_id][0] += 1
            stats[match.team_b_id][0] += 1

    ordered = sorted(team_ids, key=lambda team_id: tuple(stats[team_id]), reverse=True)
    partitions = [list(items) for _, items in groupby(ordered, key=lambda team_id: tuple(stats[team_id]))]
    if len(partitions) == 1:
        return [team_ids]

    result: list[list[int]] = []
    for partition in partitions:
        if len(partition) == 1:
            result.append(partition)
        else:
            # FIFA reapplies the mini-league criteria to only the teams still tied.
            result.extend(_resolve_head_to_head(partition, matches))
    return result


def _resolve_overall(rows: list[StandingRow], warnings: list[str]) -> list[StandingRow]:
    partitions = _partition_sort(
        rows,
        [lambda row: row.goal_difference, lambda row: row.goals_for],
    )
    result: list[StandingRow] = []
    for partition in partitions:
        result.extend(_resolve_conduct_then_rank(partition, warnings))
    return result


def _resolve_conduct_then_rank(rows: list[StandingRow], warnings: list[str]) -> list[StandingRow]:
    if len(rows) == 1:
        return rows
    if all(row.conduct_score is not None for row in rows):
        conduct_parts = _partition_sort(rows, [lambda row: int(row.conduct_score or 0)])
    else:
        warnings.append("Missing conduct data affected a tie; FIFA ranking was used provisionally.")
        conduct_parts = [rows]

    result: list[StandingRow] = []
    for partition in conduct_parts:
        if len(partition) == 1:
            result.extend(partition)
            continue
        if not all(row.fifa_rank_history for row in partition):
            raise UnresolvedTieError("FIFA ranking history is required to resolve the remaining tie")
        max_editions = max(len(row.fifa_rank_history) for row in partition)
        rank_parts = [partition]
        for edition in range(max_editions):
            next_parts: list[list[StandingRow]] = []
            for tied in rank_parts:
                if len(tied) == 1:
                    next_parts.append(tied)
                    continue
                if not all(len(row.fifa_rank_history) > edition for row in tied):
                    raise UnresolvedTieError("Additional FIFA ranking editions are required")
                ordered = sorted(tied, key=lambda row: row.fifa_rank_history[edition])
                next_parts.extend(
                    [list(items) for _, items in groupby(ordered, key=lambda row: row.fifa_rank_history[edition])]
                )
            rank_parts = next_parts
        if any(len(tied) > 1 for tied in rank_parts):
            raise UnresolvedTieError("Published FIFA ranking editions do not resolve the tie")
        result.extend(row for tied in rank_parts for row in tied)
    return result


def _partition_sort(
    rows: list[StandingRow], criteria: list[Callable[[StandingRow], int]]
) -> list[list[StandingRow]]:
    partitions = [rows]
    for criterion in criteria:
        next_partitions: list[list[StandingRow]] = []
        for partition in partitions:
            if len(partition) == 1:
                next_partitions.append(partition)
                continue
            ordered = sorted(partition, key=criterion, reverse=True)
            next_partitions.extend([list(items) for _, items in groupby(ordered, key=criterion)])
        partitions = next_partitions
    return partitions
