from __future__ import annotations

from datetime import datetime, timezone

from world_cup_api.modeling.pmsr_features import TeamMatchPmsrFeatures
from world_cup_api.modeling.pmsr_style import (
    TeamMatchStyleFeatures,
    build_team_style_profile,
    compose_style_narrative,
    compute_percentile_bounds,
    index_style_features_by_match,
    interaction_features,
    score_style_matchup,
)
from world_cup_api.modeling.pmsr_style import TeamStyleProfile


def _style_row(
    match_id: int,
    match_number: int,
    team_id: int,
    *,
    possession: float = 50.0,
    xg: float = 1.0,
) -> TeamMatchStyleFeatures:
    base = TeamMatchPmsrFeatures(
        match_id=match_id,
        official_match_number=match_number,
        team_id=team_id,
        side="team_a" if team_id == 1 else "team_b",
        scheduled_at=datetime(2026, 6, match_number, tzinfo=timezone.utc),
        possession_pct=possession,
        xg=xg,
        goals=1.0,
        shots_on_target=3.0,
        pressures=80.0,
    )
    return TeamMatchStyleFeatures(base=base, shots_total=10.0, line_team_length_m=35.0)


def test_build_team_style_profile_uses_only_prior_matches() -> None:
    features = [
        _style_row(1, 1, 1, possession=60.0),
        _style_row(1, 1, 2, possession=40.0),
        _style_row(2, 2, 1, possession=70.0),
        _style_row(2, 2, 2, possession=30.0),
    ]
    by_match = index_style_features_by_match(features)
    bounds = compute_percentile_bounds(features)
    profile = build_team_style_profile(features, by_match, team_id=1, before_match_number=2, bounds=bounds)
    assert profile is not None
    assert profile.matches_played == 1


def test_possession_vs_low_block_interaction_is_shrunk_and_clamped() -> None:
    high_possession = TeamStyleProfile(
        team_id=1,
        matches_played=3,
        attack={"possession_tendency": 0.9, "build_up_structure": 0.5, "width_crossing": 0.5,
                 "chance_central": 0.5, "tempo_counter": 0.5, "gk_build_up": 0.5,
                 "verticality": 0.5, "final_third_presence": 0.5, "chance_quality": 0.5, "pass_volume": 0.5},
        defend={"block_depth": 0.5, "press_intensity": 0.5, "press_height": 0.5, "compactness": 0.5,
                "disruption": 0.5, "solidity": 0.5, "aerial_second_balls": 0.5, "gk_sweeping": 0.5},
    )
    low_block = TeamStyleProfile(
        team_id=2,
        matches_played=3,
        attack={"possession_tendency": 0.4, "build_up_structure": 0.5, "width_crossing": 0.5,
                 "chance_central": 0.5, "tempo_counter": 0.5, "gk_build_up": 0.5,
                 "verticality": 0.5, "final_third_presence": 0.5, "chance_quality": 0.5, "pass_volume": 0.5},
        defend={"block_depth": 0.9, "press_intensity": 0.5, "press_height": 0.2, "compactness": 0.8,
                "disruption": 0.5, "solidity": 0.8, "aerial_second_balls": 0.5, "gk_sweeping": 0.5},
    )
    interactions = interaction_features(high_possession, high_possession, low_block, low_block)
    assert interactions["possession_low_block_a"] > 0.4
    matchup = score_style_matchup(high_possession, low_block, team_a_name="Spain", team_b_name="Uruguay")
    # Style edge is clamped to a small nudge, never a blowout.
    assert -0.2 <= matchup.net_xg_delta_a <= 0.2


def test_compose_style_narrative_notes_overall_favorite_when_tactics_disagree() -> None:
    narrative = compose_style_narrative(
        "England",
        "Congo DR",
        lambda_a=2.02,
        lambda_b=0.90,
        style_favor="team_b",
        delta_a=-0.08,
        interactions=(),
    )
    assert "England are favored overall" in narrative
    assert "Congo DR" in narrative
    assert "style fits better tactically" in narrative
    assert "remain favored on overall strength" in narrative
