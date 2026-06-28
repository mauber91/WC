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
from world_cup_api.modeling.pmsr_style import (
    apply_style_to_forecast,
    build_team_style_profile,
    compute_percentile_bounds,
    ensure_style_model,
    index_style_features_by_match,
    load_team_match_style_features,
)
from world_cup_api.modeling.prediction import build_forecast, knockout_win_probability
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


@dataclass(frozen=True)
class StyleBacktestReport:
    matches: int
    style_coverage: int
    baseline_log_loss: float
    form_log_loss: float
    style_log_loss: float
    xg_rmse_baseline: float
    xg_rmse_form: float
    xg_rmse_style: float
    possession_mae: float
    shots_mae: float
    sot_mae: float
    knockout_matches: int = 0
    knockout_brier_baseline: float | None = None
    knockout_brier_style: float | None = None

    def to_dict(self) -> dict[str, float | int | None]:
        return {
            "matches": self.matches,
            "style_coverage": self.style_coverage,
            "baseline_log_loss": self.baseline_log_loss,
            "form_log_loss": self.form_log_loss,
            "style_log_loss": self.style_log_loss,
            "delta_log_loss_form": self.form_log_loss - self.baseline_log_loss,
            "delta_log_loss_style": self.style_log_loss - self.baseline_log_loss,
            "xg_rmse_baseline": self.xg_rmse_baseline,
            "xg_rmse_form": self.xg_rmse_form,
            "xg_rmse_style": self.xg_rmse_style,
            "possession_mae": self.possession_mae,
            "shots_mae": self.shots_mae,
            "sot_mae": self.sot_mae,
            "knockout_matches": self.knockout_matches,
            "knockout_brier_baseline": self.knockout_brier_baseline,
            "knockout_brier_style": self.knockout_brier_style,
        }


def _rmse(errors: list[float]) -> float:
    if not errors:
        return 0.0
    arr = np.array(errors, dtype=float)
    return float(np.sqrt(np.mean(arr ** 2)))


def _mae(errors: list[float]) -> float:
    if not errors:
        return 0.0
    return float(np.mean(np.abs(errors)))


def walk_forward_style_backtest(
    db: Session,
    tournament_id: int,
    *,
    params: ContextParams = DEFAULT_CONTEXT_PARAMS,
    alpha_xg: float = 0.08,
) -> StyleBacktestReport:
    """Compare baseline, rolling-xG form, and full style model on group-stage PMSR matches."""
    baseline = baseline_elos(db, tournament_id)
    pmsr_features = load_team_match_features(db)
    pmsr_by_match = index_features_by_match(pmsr_features)
    style_features = load_team_match_style_features(db)
    style_by_match = index_style_features_by_match(style_features)
    style_model = ensure_style_model(db)
    bounds = style_model.percentile_bounds or compute_percentile_bounds(style_features)
    ingested_match_numbers = {feature.official_match_number for feature in style_features}

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
    form_probs: list[tuple[float, float, float]] = []
    style_probs: list[tuple[float, float, float]] = []
    xg_errors_baseline: list[float] = []
    xg_errors_form: list[float] = []
    xg_errors_style: list[float] = []
    possession_errors: list[float] = []
    shots_errors: list[float] = []
    sot_errors: list[float] = []
    prior_results: list[tuple[int, int, int, int]] = []
    champion_probs = champion_probs_by_team_id(db)
    style_coverage = 0

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
            pmsr_features, pmsr_by_match, match.team_a_id, match.official_match_number,
        )
        rolling_b = team_rolling_features(
            pmsr_features, pmsr_by_match, match.team_b_id, match.official_match_number,
        )
        form_forecast = apply_pmsr_to_forecast(
            forecast, rolling_a, rolling_b, alpha_xg=alpha_xg, goal_dispersion=params.goal_dispersion,
        )
        profile_a = build_team_style_profile(
            style_features, style_by_match, match.team_a_id, match.official_match_number, bounds,
        )
        profile_b = build_team_style_profile(
            style_features, style_by_match, match.team_b_id, match.official_match_number, bounds,
        )
        style_forecast = forecast
        tactical = None
        if profile_a and profile_b:
            style_forecast, tactical, _ = apply_style_to_forecast(
                forecast,
                profile_a,
                profile_b,
                goal_dispersion=params.goal_dispersion,
                model=style_model,
            )

        actual_xg_a = next(
            (row.base.xg for row in style_features if row.match_id == match.id and row.team_id == match.team_a_id),
            None,
        )
        actual_xg_b = next(
            (row.base.xg for row in style_features if row.match_id == match.id and row.team_id == match.team_b_id),
            None,
        )
        if actual_xg_a is not None and actual_xg_b is not None:
            xg_errors_baseline.extend([
                (forecast.lambda_a - actual_xg_a) ** 2,
                (forecast.lambda_b - actual_xg_b) ** 2,
            ])
            xg_errors_form.extend([
                (form_forecast.lambda_a - actual_xg_a) ** 2,
                (form_forecast.lambda_b - actual_xg_b) ** 2,
            ])
            xg_errors_style.extend([
                (style_forecast.lambda_a - actual_xg_a) ** 2,
                (style_forecast.lambda_b - actual_xg_b) ** 2,
            ])
            if tactical is not None:
                row_a = style_by_match.get(match.id, {}).get(match.team_a_id)
                row_b = style_by_match.get(match.id, {}).get(match.team_b_id)
                if row_a and row_a.base.possession_pct is not None:
                    possession_errors.append(abs(tactical.possession_a - row_a.base.possession_pct))
                if row_a and row_b:
                    shots_errors.append(abs(tactical.shots_a - (row_a.shots_total or 0)))
                    shots_errors.append(abs(tactical.shots_b - (row_b.shots_total or 0)))
                    # The PMSR "shots_on_target" field is actually total attempts;
                    # derive the SOT actual the same way as the model (33% of shots).
                    sot_errors.append(abs(tactical.sot_a - (row_a.shots_total or 0) * 0.33))
                    sot_errors.append(abs(tactical.sot_b - (row_b.shots_total or 0) * 0.33))

        actuals.append(_outcome_index(result.team_a_goals_90, result.team_b_goals_90))
        baseline_probs.append(forecast.final)
        form_probs.append(form_forecast.final)
        style_probs.append(style_forecast.final)
        if match.official_match_number in ingested_match_numbers and profile_a and profile_b:
            style_coverage += 1

        prior_results.append((
            match.team_a_id,
            match.team_b_id,
            result.team_a_goals_90,
            result.team_b_goals_90,
        ))

    if not actuals:
        raise ValueError("No finished group matches to backtest")

    actual_array = np.array(actuals)
    knockout_finished = db.execute(
        select(Match, MatchResult)
        .join(MatchResult, MatchResult.match_id == Match.id)
        .where(
            Match.tournament_id == tournament_id,
            Match.group_id.is_(None),
            MatchResult.is_current.is_(True),
            Match.team_a_id.is_not(None),
            Match.team_b_id.is_not(None),
        )
    ).all()
    knockout_brier_baseline = None
    knockout_brier_style = None
    if knockout_finished:
        brier_base: list[float] = []
        brier_style: list[float] = []
        for match, result in knockout_finished:
            team_a = db.get(Team, match.team_a_id)
            team_b = db.get(Team, match.team_b_id)
            assert team_a is not None and team_b is not None
            strength_a = fuse_strength(
                baseline[match.team_a_id],
                _fifa_rank(db, match.team_a_id),
                fifa_weight=params.fifa_strength_weight,
                champion_prob=champion_probs.get(match.team_a_id),
                champion_weight=params.champion_strength_weight,
                champion_field_size=params.champion_field_size,
            )
            strength_b = fuse_strength(
                baseline[match.team_b_id],
                _fifa_rank(db, match.team_b_id),
                fifa_weight=params.fifa_strength_weight,
                champion_prob=champion_probs.get(match.team_b_id),
                champion_weight=params.champion_strength_weight,
                champion_field_size=params.champion_field_size,
            )
            host_a, host_b = venue_home_flags(team_a.country_code, team_b.country_code, match.host_country)
            base_fc = build_forecast(
                strength_a, strength_b, host_a=host_a, host_b=host_b,
                goal_dispersion=params.goal_dispersion, market_blend_alpha=0.0,
            )
            profile_a = build_team_style_profile(
                style_features, style_by_match, match.team_a_id, match.official_match_number, bounds,
            )
            profile_b = build_team_style_profile(
                style_features, style_by_match, match.team_b_id, match.official_match_number, bounds,
            )
            style_fc = base_fc
            if profile_a and profile_b:
                style_fc, _, _ = apply_style_to_forecast(
                    base_fc, profile_a, profile_b, goal_dispersion=params.goal_dispersion, model=style_model,
                )
            actual = 1.0 if result.winner_team_id == match.team_a_id else 0.0
            p_base = knockout_win_probability(base_fc)
            p_style = knockout_win_probability(style_fc)
            brier_base.append((p_base - actual) ** 2)
            brier_style.append((p_style - actual) ** 2)
        knockout_brier_baseline = float(np.mean(brier_base))
        knockout_brier_style = float(np.mean(brier_style))

    return StyleBacktestReport(
        matches=len(actuals),
        style_coverage=style_coverage,
        baseline_log_loss=evaluate_probabilities(actual_array, np.array(baseline_probs)).log_loss,
        form_log_loss=evaluate_probabilities(actual_array, np.array(form_probs)).log_loss,
        style_log_loss=evaluate_probabilities(actual_array, np.array(style_probs)).log_loss,
        xg_rmse_baseline=_rmse(xg_errors_baseline),
        xg_rmse_form=_rmse(xg_errors_form),
        xg_rmse_style=_rmse(xg_errors_style),
        possession_mae=_mae(possession_errors),
        shots_mae=_mae(shots_errors),
        sot_mae=_mae(sot_errors),
        knockout_matches=len(knockout_finished),
        knockout_brier_baseline=knockout_brier_baseline,
        knockout_brier_style=knockout_brier_style,
    )
