from __future__ import annotations

from datetime import date

import pytest

from world_cup_api.domain.squad_rating import InjuryRecord, composite_rating, injury_penalty, season_performance_score


def test_season_performance_weights_recent_season_more() -> None:
    recent_heavy = season_performance_score(8.0, 6.0, 6.0)
    old_heavy = season_performance_score(6.0, 6.0, 8.0)
    assert recent_heavy > old_heavy


def test_injury_penalty_favors_recent_lengthy_injuries() -> None:
    reference = date(2026, 6, 11)
    recent = injury_penalty([
        InjuryRecord(date(2026, 3, 1), date(2026, 4, 15), 45),
    ], reference)
    old = injury_penalty([
        InjuryRecord(date(2025, 6, 1), date(2025, 7, 15), 45),
    ], reference)
    assert recent > old


def test_short_injuries_do_not_penalize() -> None:
    reference = date(2026, 6, 11)
    assert injury_penalty([
        InjuryRecord(date(2026, 5, 1), date(2026, 5, 10), 9),
    ], reference) == 0.0


def test_composite_rating_clamped_to_1_99() -> None:
    rating = composite_rating(95, 150, 8.0, 7.8, 7.5, [], date(2026, 6, 11))
    assert 1 <= rating <= 99


def test_composite_rating_drops_with_lengthy_injuries() -> None:
    healthy = composite_rating(85, 40, 7.2, 7.0, 6.8, [], date(2026, 6, 11))
    injured = composite_rating(85, 40, 7.2, 7.0, 6.8, [
        InjuryRecord(date(2026, 2, 1), date(2026, 6, 5), 120),
    ], date(2026, 6, 11))
    assert injured < healthy
