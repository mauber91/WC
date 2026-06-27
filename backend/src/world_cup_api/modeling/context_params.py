from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContextParams:
    beta_rest: float = 0.06
    rest_cap_days: float = 4.0
    beta_travel: float = 0.05
    travel_ref_km: float = 3500.0
    elo_sigma_base: float = 35.0
    rotation_elo_penalty: float = 55.0
    rotation_elo_locked_first: float = 60.0
    rotation_elo_clinched: float = 30.0
    rotation_elo_eliminated: float = 40.0
    collusion_draw_boost: float = 0.18
    goal_dispersion: float = 0.15
    fifa_strength_weight: float = 0.06
    champion_strength_weight: float = 0.08
    champion_field_size: int = 48
    market_blend_alpha: float = 0.85
    clinch_points: int = 6
    elim_points: int = 0


DEFAULT_CONTEXT_PARAMS = ContextParams()


def rest_curve(rest_days: float, *, cap: float = DEFAULT_CONTEXT_PARAMS.rest_cap_days) -> float:
    if rest_days <= 0:
        return 0.0
    return min(rest_days, cap) / cap


def travel_curve(travel_km: float, *, ref: float = DEFAULT_CONTEXT_PARAMS.travel_ref_km) -> float:
    if travel_km <= 0:
        return 0.0
    return min(travel_km, ref) / ref


def elo_sigma(confederation: str, *, base: float = DEFAULT_CONTEXT_PARAMS.elo_sigma_base) -> float:
    # Wider uncertainty for teams with less frequent top-tier competitive data.
    multipliers = {
        "UEFA": 1.0,
        "CONMEBOL": 1.0,
        "AFC": 1.15,
        "CAF": 1.15,
        "CONCACAF": 1.1,
        "OFC": 1.35,
    }
    return base * multipliers.get(confederation.upper(), 1.2)
