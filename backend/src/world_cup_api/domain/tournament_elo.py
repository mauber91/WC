from __future__ import annotations

from collections.abc import Iterable

# Group-stage results move strength within the tournament; K is tuned for single-match updates.
DEFAULT_K = 32.0


def expected_score(elo_a: float, elo_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((elo_b - elo_a) / 400))


def match_scores(goals_a: int, goals_b: int) -> tuple[float, float]:
    if goals_a > goals_b:
        return 1.0, 0.0
    if goals_a < goals_b:
        return 0.0, 1.0
    return 0.5, 0.5


def margin_multiplier(goals_a: int, goals_b: int) -> float:
    diff = abs(goals_a - goals_b)
    if diff <= 1:
        return 1.0
    return min(1.75, 1.0 + 0.15 * (diff - 1))


def apply_match_result(
    elos: dict[int, float],
    team_a: int,
    team_b: int,
    goals_a: int,
    goals_b: int,
    *,
    k: float = DEFAULT_K,
) -> None:
    rating_a = elos[team_a]
    rating_b = elos[team_b]
    score_a, score_b = match_scores(goals_a, goals_b)
    expected_a = expected_score(rating_a, rating_b)
    expected_b = 1.0 - expected_a
    multiplier = margin_multiplier(goals_a, goals_b)
    elos[team_a] = rating_a + k * multiplier * (score_a - expected_a)
    elos[team_b] = rating_b + k * multiplier * (score_b - expected_b)


def build_elo_table(
    baseline: dict[int, float],
    results: Iterable[tuple[int, int, int, int]],
    *,
    k: float = DEFAULT_K,
) -> dict[int, float]:
    elos = dict(baseline)
    for team_a, team_b, goals_a, goals_b in results:
        apply_match_result(elos, team_a, team_b, goals_a, goals_b, k=k)
    return elos
