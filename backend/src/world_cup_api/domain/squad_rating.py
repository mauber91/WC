from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timezone

SEASON_WEIGHTS = (0.50, 0.30, 0.20)
LENGTHY_INJURY_DAYS = 14
MARKET_VALUE_LOG_MIN = 0.05
MARKET_VALUE_LOG_MAX = 200.0

FC26_WEIGHT = 0.38
MARKET_WEIGHT = 0.12
SEASON_WEIGHT = 0.50
INJURY_WEIGHT = 0.05


@dataclass(frozen=True)
class InjuryRecord:
    started_on: date
    ended_on: date | None
    days_out: int


def normalize_market_value(value_meur: float) -> float:
    """Map transfer-market value (€m) to a 1–99 scale via log scaling."""
    if value_meur <= 0:
        return 45.0
    log_val = math.log10(max(value_meur, MARKET_VALUE_LOG_MIN))
    log_min = math.log10(MARKET_VALUE_LOG_MIN)
    log_max = math.log10(MARKET_VALUE_LOG_MAX)
    scaled = 40.0 + 59.0 * (log_val - log_min) / (log_max - log_min)
    return max(1.0, min(99.0, scaled))


def season_performance_score(
    season_2025_26: float | None,
    season_2024_25: float | None,
    season_2023_24: float | None,
) -> float:
    """Weighted blend of last three season ratings (0–10 scale) mapped to 1–99."""
    ratings = (season_2025_26, season_2024_25, season_2023_24)
    available = [(weight, rating) for weight, rating in zip(SEASON_WEIGHTS, ratings) if rating is not None]
    if not available:
        return 50.0
    total_weight = sum(weight for weight, _ in available)
    weighted = sum(weight * rating for weight, rating in available) / total_weight
    return max(1.0, min(99.0, weighted * 9.8 + 1.0))


def injury_penalty(injuries: list[InjuryRecord], as_of: date | None = None) -> float:
    """
    Penalty for lengthy injuries (14+ days) in the last 12 months.
    Recent injuries carry exponentially more weight.
    Returns 0–20 penalty points before weighting.
    """
    reference = as_of or datetime.now(timezone.utc).date()
    from datetime import timedelta

    window_start = reference - timedelta(days=365)
    penalty = 0.0
    for injury in injuries:
        if injury.days_out < LENGTHY_INJURY_DAYS:
            continue
        injury_end = injury.ended_on or reference
        if injury_end < window_start:
            continue
        days_since_end = max(0, (reference - injury_end).days)
        recency = math.exp(-days_since_end / 120.0)
        severity = injury.days_out / 30.0
        penalty += severity * recency * 2.5
    return min(20.0, penalty)


def composite_rating(
    fc26_overall: int,
    market_value_meur: float,
    season_2025_26: float | None,
    season_2024_25: float | None,
    season_2023_24: float | None,
    injuries: list[InjuryRecord],
    as_of: date | None = None,
) -> int:
    fc26 = max(1, min(99, fc26_overall))
    market = normalize_market_value(market_value_meur)
    season = season_performance_score(season_2025_26, season_2024_25, season_2023_24)
    injury = injury_penalty(injuries, as_of)
    raw = (
        FC26_WEIGHT * fc26
        + MARKET_WEIGHT * market
        + SEASON_WEIGHT * season
        - INJURY_WEIGHT * injury
    )
    return max(1, min(99, round(raw)))
