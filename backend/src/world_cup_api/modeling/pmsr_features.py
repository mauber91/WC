from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import exp
from statistics import mean
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from world_cup_api.db.models import Match, Team
from world_cup_api.db.report_models import (
    MatchReportDocument,
    MatchReportEvent,
    MatchReportExtractionRun,
    MatchReportObservation,
)

if TYPE_CHECKING:
    from world_cup_api.modeling.prediction import MatchForecast

MIN_CONFIDENCE = 0.80

SUMMARY_METRIC_FIELDS: dict[str, str] = {
    "summary.possession": "possession_pct",
    "summary.xg_expected_goals": "xg",
    "summary.goals": "goals",
    "summary.attempts_at_goal_on_target": "shots_on_target",
    "summary.total_passes_complete": "passes_complete",
    "summary.pass_completion_percent": "pass_completion_pct",
    "summary.defensive_pressures_applied_direct_pressures": "pressures",
    "summary.crosses": "crosses",
}

EVENT_COUNT_FIELDS: dict[str, str] = {
    "attempt_spatial": "attempt_spatial_count",
    "pressure": "pressure_count",
    "cross": "cross_event_count",
}

# Legacy extractions tagged left/right columns as Brazil/Haiti before team resolution.
_EXTRACTOR_SIDE_CODES = ("BRA", "HAI")


def _extractor_side_team_ids(session: Session) -> dict[int, str]:
    rows = session.scalars(select(Team).where(Team.fifa_code.in_(_EXTRACTOR_SIDE_CODES))).all()
    by_code = {team.fifa_code: team.id for team in rows}
    mapping: dict[int, str] = {}
    if "BRA" in by_code:
        mapping[by_code["BRA"]] = "team_a"
    if "HAI" in by_code:
        mapping[by_code["HAI"]] = "team_b"
    return mapping


def _resolve_match_team_id(
    observation_team_id: int,
    match_team_a_id: int,
    match_team_b_id: int,
    side_team_ids: dict[int, str],
) -> int:
    if observation_team_id in (match_team_a_id, match_team_b_id):
        return observation_team_id
    side = side_team_ids.get(observation_team_id)
    if side == "team_a":
        return match_team_a_id
    if side == "team_b":
        return match_team_b_id
    return observation_team_id


@dataclass(frozen=True)
class TeamMatchPmsrFeatures:
    match_id: int
    official_match_number: int
    team_id: int
    side: str
    scheduled_at: object
    possession_pct: float | None = None
    xg: float | None = None
    goals: float | None = None
    shots_on_target: float | None = None
    passes_complete: float | None = None
    pass_completion_pct: float | None = None
    pressures: float | None = None
    crosses: float | None = None
    attempt_spatial_count: int = 0
    pressure_count: int = 0
    cross_event_count: int = 0
    extraction_quality: float | None = None


@dataclass(frozen=True)
class TeamRollingPmsrFeatures:
    team_id: int
    matches_played: int
    possession_pct: float | None
    xg_for: float | None
    xg_against: float | None
    goals_for: float | None
    goals_against: float | None
    shots_on_target: float | None
    pressures: float | None
    attempt_spatial_count: float | None


def _average(values: list[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return float(mean(present))


def load_team_match_features(
    session: Session,
    *,
    min_confidence: float = MIN_CONFIDENCE,
) -> list[TeamMatchPmsrFeatures]:
    """Pivot active PMSR extractions into one row per (match, team)."""
    documents = session.execute(
        select(
            MatchReportDocument.match_id,
            MatchReportDocument.official_match_number,
            Match.team_a_id,
            Match.team_b_id,
            Match.scheduled_at,
            MatchReportExtractionRun.id,
            MatchReportExtractionRun.quality_score,
        )
        .join(
            MatchReportExtractionRun,
            (MatchReportExtractionRun.document_id == MatchReportDocument.id)
            & MatchReportExtractionRun.is_active.is_(True),
        )
        .join(Match, Match.id == MatchReportDocument.match_id)
        .where(MatchReportDocument.match_id.is_not(None))
        .order_by(Match.official_match_number)
    ).all()
    if not documents:
        return []

    side_team_ids = _extractor_side_team_ids(session)
    run_ids = [row.id for row in documents]
    document_by_run = {row.id: row for row in documents}
    metric_keys = tuple(SUMMARY_METRIC_FIELDS)

    observations = session.scalars(
        select(MatchReportObservation).where(
            MatchReportObservation.run_id.in_(run_ids),
            MatchReportObservation.scope == "team",
            MatchReportObservation.team_id.is_not(None),
            MatchReportObservation.confidence >= min_confidence,
            MatchReportObservation.metric_key.in_(metric_keys),
        )
    ).all()
    obs_by_run_team: dict[tuple[str, int], dict[str, float | None]] = defaultdict(dict)
    for observation in observations:
        assert observation.team_id is not None
        document_row = document_by_run[observation.run_id]
        assert document_row.team_a_id is not None and document_row.team_b_id is not None
        team_id = _resolve_match_team_id(
            observation.team_id,
            document_row.team_a_id,
            document_row.team_b_id,
            side_team_ids,
        )
        obs_by_run_team[(observation.run_id, team_id)][observation.metric_key] = observation.value_numeric

    event_rows = session.execute(
        select(
            MatchReportEvent.run_id,
            MatchReportEvent.team_id,
            MatchReportEvent.event_type,
            func.count(),
        )
        .where(
            MatchReportEvent.run_id.in_(run_ids),
            MatchReportEvent.team_id.is_not(None),
            MatchReportEvent.event_type.in_(tuple(EVENT_COUNT_FIELDS)),
        )
        .group_by(MatchReportEvent.run_id, MatchReportEvent.team_id, MatchReportEvent.event_type)
    ).all()
    events_by_run_team: dict[tuple[str, int], dict[str, int]] = defaultdict(dict)
    for run_id, team_id, event_type, count in event_rows:
        assert team_id is not None
        document_row = document_by_run[run_id]
        assert document_row.team_a_id is not None and document_row.team_b_id is not None
        resolved_team_id = _resolve_match_team_id(
            team_id,
            document_row.team_a_id,
            document_row.team_b_id,
            side_team_ids,
        )
        events_by_run_team[(run_id, resolved_team_id)][event_type] = int(count)

    features: list[TeamMatchPmsrFeatures] = []
    for row in documents:
        assert row.match_id is not None
        assert row.team_a_id is not None and row.team_b_id is not None
        for team_id, side in ((row.team_a_id, "team_a"), (row.team_b_id, "team_b")):
            metrics = obs_by_run_team.get((row.id, team_id), {})
            events = events_by_run_team.get((row.id, team_id), {})
            kwargs: dict[str, float | int | None] = {
                field: metrics.get(metric_key)
                for metric_key, field in SUMMARY_METRIC_FIELDS.items()
            }
            for event_type, field in EVENT_COUNT_FIELDS.items():
                kwargs[field] = events.get(event_type, 0)
            features.append(
                TeamMatchPmsrFeatures(
                    match_id=row.match_id,
                    official_match_number=row.official_match_number or 0,
                    team_id=team_id,
                    side=side,
                    scheduled_at=row.scheduled_at,
                    extraction_quality=row.quality_score,
                    **kwargs,  # type: ignore[arg-type]
                )
            )
    return features


def index_features_by_match(
    features: list[TeamMatchPmsrFeatures],
) -> dict[int, dict[int, TeamMatchPmsrFeatures]]:
    indexed: dict[int, dict[int, TeamMatchPmsrFeatures]] = defaultdict(dict)
    for feature in features:
        indexed[feature.match_id][feature.team_id] = feature
    return dict(indexed)


def team_rolling_features(
    features: list[TeamMatchPmsrFeatures],
    by_match: dict[int, dict[int, TeamMatchPmsrFeatures]],
    team_id: int,
    before_match_number: int,
    *,
    window: int | None = None,
) -> TeamRollingPmsrFeatures | None:
    """Lag-only rolling averages from prior ingested reports (no same-match leakage)."""
    prior = [
        feature
        for feature in features
        if feature.team_id == team_id and feature.official_match_number < before_match_number
    ]
    prior.sort(key=lambda item: item.official_match_number)
    if window is not None:
        prior = prior[-window:]
    if not prior:
        return None

    xg_for: list[float | None] = []
    xg_against: list[float | None] = []
    goals_for: list[float | None] = []
    goals_against: list[float | None] = []
    for feature in prior:
        opponents = by_match.get(feature.match_id, {})
        opponent_id = next(
            (other_team_id for other_team_id in opponents if other_team_id != team_id),
            None,
        )
        opponent = opponents.get(opponent_id) if opponent_id is not None else None
        xg_for.append(feature.xg)
        goals_for.append(feature.goals)
        xg_against.append(opponent.xg if opponent else None)
        goals_against.append(opponent.goals if opponent else None)

    return TeamRollingPmsrFeatures(
        team_id=team_id,
        matches_played=len(prior),
        possession_pct=_average([item.possession_pct for item in prior]),
        xg_for=_average(xg_for),
        xg_against=_average(xg_against),
        goals_for=_average(goals_for),
        goals_against=_average(goals_against),
        shots_on_target=_average([item.shots_on_target for item in prior]),
        pressures=_average([item.pressures for item in prior]),
        attempt_spatial_count=_average([float(item.attempt_spatial_count) for item in prior]),
    )


def adjust_expected_goals_with_pmsr(
    lambda_a: float,
    lambda_b: float,
    rolling_a: TeamRollingPmsrFeatures | None,
    rolling_b: TeamRollingPmsrFeatures | None,
    *,
    alpha_xg: float = 0.08,
) -> tuple[float, float]:
    """Shift pre-match expected goals using lagged xG balance from prior reports."""

    def _shift(lambda_value: float, rolling: TeamRollingPmsrFeatures | None) -> float:
        if rolling is None or rolling.xg_for is None or rolling.xg_against is None:
            return lambda_value
        net_xg = rolling.xg_for - rolling.xg_against
        return float(lambda_value * exp(alpha_xg * net_xg))

    return _shift(lambda_a, rolling_a), _shift(lambda_b, rolling_b)


def apply_pmsr_to_forecast(
    forecast: MatchForecast,
    rolling_a: TeamRollingPmsrFeatures | None,
    rolling_b: TeamRollingPmsrFeatures | None,
    *,
    alpha_xg: float = 0.08,
    goal_dispersion: float = 0.0,
    market_blend_alpha: float = 0.0,
) -> MatchForecast:
    """Recompute 1X2 probabilities after lagged PMSR xG adjustment."""
    from world_cup_api.modeling.prediction import MatchForecast, blend, one_x_two, reweight_score_matrix, score_matrix

    lambda_a, lambda_b = adjust_expected_goals_with_pmsr(
        forecast.lambda_a,
        forecast.lambda_b,
        rolling_a,
        rolling_b,
        alpha_xg=alpha_xg,
    )
    if lambda_a == forecast.lambda_a and lambda_b == forecast.lambda_b:
        return forecast
    raw_matrix = score_matrix(lambda_a, lambda_b, goal_dispersion=goal_dispersion)
    model = one_x_two(raw_matrix)
    final = blend(model, forecast.market, alpha=market_blend_alpha)
    matrix = reweight_score_matrix(raw_matrix, final)
    return MatchForecast(
        lambda_a,
        lambda_b,
        model,
        forecast.market,
        final,
        tuple(tuple(float(value) for value in row) for row in matrix),
    )
