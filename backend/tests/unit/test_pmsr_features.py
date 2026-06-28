from __future__ import annotations

from datetime import datetime, timezone

from world_cup_api.modeling.pmsr_features import (
    TeamMatchPmsrFeatures,
    adjust_expected_goals_with_pmsr,
    index_features_by_match,
    team_rolling_features,
)


def _feature(
    match_id: int,
    match_number: int,
    team_id: int,
    *,
    xg: float | None = None,
    goals: float | None = None,
) -> TeamMatchPmsrFeatures:
    return TeamMatchPmsrFeatures(
        match_id=match_id,
        official_match_number=match_number,
        team_id=team_id,
        side="team_a" if team_id == 1 else "team_b",
        scheduled_at=datetime(2026, 6, match_number, tzinfo=timezone.utc),
        xg=xg,
        goals=goals,
    )


def test_team_rolling_features_uses_only_prior_matches() -> None:
    features = [
        _feature(1, 1, 1, xg=1.5, goals=2),
        _feature(1, 1, 2, xg=0.8, goals=0),
        _feature(2, 2, 1, xg=2.0, goals=3),
        _feature(2, 2, 2, xg=1.0, goals=1),
    ]
    by_match = index_features_by_match(features)
    rolling = team_rolling_features(features, by_match, team_id=1, before_match_number=2)
    assert rolling is not None
    assert rolling.matches_played == 1
    assert rolling.xg_for == 1.5
    assert rolling.xg_against == 0.8


def test_team_rolling_features_returns_none_without_history() -> None:
    features = [_feature(1, 1, 1, xg=1.0)]
    by_match = index_features_by_match(features)
    assert team_rolling_features(features, by_match, team_id=1, before_match_number=1) is None


def test_resolve_match_team_id_maps_extractor_placeholders() -> None:
    from world_cup_api.modeling.pmsr_features import _resolve_match_team_id

    side_team_ids = {9: "team_a", 11: "team_b"}
    assert _resolve_match_team_id(9, 1, 2, side_team_ids) == 1
    assert _resolve_match_team_id(11, 1, 2, side_team_ids) == 2
    assert _resolve_match_team_id(1, 1, 2, side_team_ids) == 1


def test_adjust_expected_goals_with_pmsr_shifts_toward_positive_xg_balance() -> None:
    from world_cup_api.modeling.pmsr_features import TeamRollingPmsrFeatures

    rolling = TeamRollingPmsrFeatures(
        team_id=1,
        matches_played=2,
        possession_pct=55.0,
        xg_for=2.0,
        xg_against=0.5,
        goals_for=3.0,
        goals_against=1.0,
        shots_on_target=6.0,
        pressures=120.0,
        attempt_spatial_count=10.0,
    )
    lambda_a, lambda_b = adjust_expected_goals_with_pmsr(1.3, 1.1, rolling, None, alpha_xg=0.1)
    assert lambda_a > 1.3
    assert lambda_b == 1.1
