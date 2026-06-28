from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from world_cup_api.db.models import Match, MatchResult, Team
from world_cup_api.domain.host_advantage import venue_home_flags
from world_cup_api.domain.team_strength import fuse_strength
from world_cup_api.domain.tournament_elo import build_elo_table
from world_cup_api.modeling.context_params import ContextParams, DEFAULT_CONTEXT_PARAMS
from world_cup_api.modeling.evaluation import EvaluationMetrics, evaluate_probabilities
from world_cup_api.modeling.pmsr_features import (
    apply_pmsr_to_forecast,
    index_features_by_match,
    load_team_match_features,
    team_rolling_features,
)
from world_cup_api.modeling.prediction import build_forecast
from world_cup_api.services.tournament_elo import baseline_elos
from world_cup_api.services.champion_market_sync import champion_probs_by_team_id


@dataclass(frozen=True)
class BacktestReport:
    matches: int
    metrics: EvaluationMetrics

    def to_dict(self) -> dict[str, float | int]:
        return {"matches": self.matches, **self.metrics.to_dict()}


@dataclass(frozen=True)
class PmsrBacktestComparison:
    matches: int
    pmsr_coverage: int
    baseline: EvaluationMetrics
    pmsr_adjusted: EvaluationMetrics

    def to_dict(self) -> dict[str, float | int]:
        return {
            "matches": self.matches,
            "pmsr_coverage": self.pmsr_coverage,
            **{f"baseline_{key}": value for key, value in self.baseline.to_dict().items()},
            **{f"pmsr_{key}": value for key, value in self.pmsr_adjusted.to_dict().items()},
        }


def _outcome_index(goals_a: int, goals_b: int) -> int:
    if goals_a > goals_b:
        return 0
    if goals_a < goals_b:
        return 2
    return 1


def _fifa_rank(db: Session, team_id: int) -> float:
    from world_cup_api.services.predictions import _latest_fifa_rank

    return _latest_fifa_rank(db, team_id, 50)

def walk_forward_group_backtest(
    db: Session,
    tournament_id: int,
    *,
    params: ContextParams = DEFAULT_CONTEXT_PARAMS,
) -> BacktestReport:
    """Walk-forward 1X2 log-loss on finished group matches (pre-match Elos only)."""
    baseline = baseline_elos(db, tournament_id)
    finished = db.execute(
        select(Match, MatchResult)
        .join(MatchResult, MatchResult.match_id == Match.id)
        .where(
            Match.tournament_id == tournament_id,
            Match.group_id.is_not(None),
            MatchResult.is_current.is_(True),
            Match.team_a_id.is_not(None),
            Match.team_b_id.is_not(None),
        )
        .order_by(Match.scheduled_at, Match.official_match_number)
    ).all()

    actuals: list[int] = []
    probabilities: list[tuple[float, float, float]] = []
    prior_results: list[tuple[int, int, int, int]] = []
    champion_probs = champion_probs_by_team_id(db)

    for match, result in finished:
        team_a = db.get(Team, match.team_a_id)
        team_b = db.get(Team, match.team_b_id)
        assert team_a is not None and team_b is not None

        pre_match_elos = build_elo_table(baseline, prior_results)
        strength_a = fuse_strength(
            pre_match_elos[match.team_a_id],
            _fifa_rank(db, match.team_a_id),
            fifa_weight=params.fifa_strength_weight,
            champion_prob=champion_probs.get(match.team_a_id),
            champion_weight=params.champion_strength_weight,
            champion_field_size=params.champion_field_size,
        )
        strength_b = fuse_strength(
            pre_match_elos[match.team_b_id],
            _fifa_rank(db, match.team_b_id),
            fifa_weight=params.fifa_strength_weight,
            champion_prob=champion_probs.get(match.team_b_id),
            champion_weight=params.champion_strength_weight,
            champion_field_size=params.champion_field_size,
        )
        host_a, host_b = venue_home_flags(team_a.country_code, team_b.country_code, match.host_country)
        forecast = build_forecast(
            strength_a,
            strength_b,
            host_a=host_a,
            host_b=host_b,
            goal_dispersion=params.goal_dispersion,
            market_blend_alpha=0.0,
        )
        actuals.append(_outcome_index(result.team_a_goals_90, result.team_b_goals_90))
        probabilities.append(forecast.final)

        prior_results.append((
            match.team_a_id,
            match.team_b_id,
            result.team_a_goals_90,
            result.team_b_goals_90,
        ))

    if not actuals:
        raise ValueError("No finished group matches to backtest")

    metrics = evaluate_probabilities(np.array(actuals), np.array(probabilities))
    return BacktestReport(matches=len(actuals), metrics=metrics)


def walk_forward_pmsr_backtest(
    db: Session,
    tournament_id: int,
    *,
    params: ContextParams = DEFAULT_CONTEXT_PARAMS,
    alpha_xg: float = 0.08,
    rolling_window: int | None = None,
) -> PmsrBacktestComparison:
    """Compare baseline Elo forecasts to lagged PMSR xG-adjusted forecasts."""
    baseline = baseline_elos(db, tournament_id)
    pmsr_features = load_team_match_features(db)
    by_match = index_features_by_match(pmsr_features)
    ingested_match_numbers = {feature.official_match_number for feature in pmsr_features}

    finished = db.execute(
        select(Match, MatchResult)
        .join(MatchResult, MatchResult.match_id == Match.id)
        .where(
            Match.tournament_id == tournament_id,
            Match.group_id.is_not(None),
            MatchResult.is_current.is_(True),
            Match.team_a_id.is_not(None),
            Match.team_b_id.is_not(None),
        )
        .order_by(Match.scheduled_at, Match.official_match_number)
    ).all()

    actuals: list[int] = []
    baseline_probs: list[tuple[float, float, float]] = []
    pmsr_probs: list[tuple[float, float, float]] = []
    prior_results: list[tuple[int, int, int, int]] = []
    champion_probs = champion_probs_by_team_id(db)
    pmsr_coverage = 0

    for match, result in finished:
        team_a = db.get(Team, match.team_a_id)
        team_b = db.get(Team, match.team_b_id)
        assert team_a is not None and team_b is not None

        pre_match_elos = build_elo_table(baseline, prior_results)
        strength_a = fuse_strength(
            pre_match_elos[match.team_a_id],
            _fifa_rank(db, match.team_a_id),
            fifa_weight=params.fifa_strength_weight,
            champion_prob=champion_probs.get(match.team_a_id),
            champion_weight=params.champion_strength_weight,
            champion_field_size=params.champion_field_size,
        )
        strength_b = fuse_strength(
            pre_match_elos[match.team_b_id],
            _fifa_rank(db, match.team_b_id),
            fifa_weight=params.fifa_strength_weight,
            champion_prob=champion_probs.get(match.team_b_id),
            champion_weight=params.champion_strength_weight,
            champion_field_size=params.champion_field_size,
        )
        host_a, host_b = venue_home_flags(team_a.country_code, team_b.country_code, match.host_country)
        forecast = build_forecast(
            strength_a,
            strength_b,
            host_a=host_a,
            host_b=host_b,
            goal_dispersion=params.goal_dispersion,
            market_blend_alpha=0.0,
        )
        rolling_a = team_rolling_features(
            pmsr_features,
            by_match,
            match.team_a_id,
            match.official_match_number,
            window=rolling_window,
        )
        rolling_b = team_rolling_features(
            pmsr_features,
            by_match,
            match.team_b_id,
            match.official_match_number,
            window=rolling_window,
        )
        pmsr_forecast = apply_pmsr_to_forecast(
            forecast,
            rolling_a,
            rolling_b,
            alpha_xg=alpha_xg,
            goal_dispersion=params.goal_dispersion,
        )

        actuals.append(_outcome_index(result.team_a_goals_90, result.team_b_goals_90))
        baseline_probs.append(forecast.final)
        pmsr_probs.append(pmsr_forecast.final)
        if match.official_match_number in ingested_match_numbers and rolling_a and rolling_b:
            pmsr_coverage += 1

        prior_results.append((
            match.team_a_id,
            match.team_b_id,
            result.team_a_goals_90,
            result.team_b_goals_90,
        ))

    if not actuals:
        raise ValueError("No finished group matches to backtest")

    actual_array = np.array(actuals)
    return PmsrBacktestComparison(
        matches=len(actuals),
        pmsr_coverage=pmsr_coverage,
        baseline=evaluate_probabilities(actual_array, np.array(baseline_probs)),
        pmsr_adjusted=evaluate_probabilities(actual_array, np.array(pmsr_probs)),
    )
