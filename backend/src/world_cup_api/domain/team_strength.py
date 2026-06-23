from __future__ import annotations

"""Fuse Elo and FIFA rank into a single pre-match strength (Elo scale)."""

from world_cup_api.domain.champion_markets import champion_probability_to_elo

# Bookmakers generated from our model — not independent market information.
SYNTHETIC_BOOKMAKERS = frozenset({"model-consensus"})


def fifa_rank_to_elo(rank: float) -> float:
    """Map FIFA rank (1 = best) to approximate Elo scale."""
    return 2200.0 - 15.0 * rank


def fuse_strength(
    elo: float,
    fifa_rank: float,
    *,
    fifa_weight: float,
    champion_prob: float | None = None,
    champion_weight: float = 0.0,
    champion_field_size: int = 48,
) -> float:
    """Blend live/baseline Elo with FIFA-implied strength and WC winner market."""
    if fifa_weight <= 0:
        base = elo
    else:
        fifa_elo = fifa_rank_to_elo(fifa_rank)
        base = (1.0 - fifa_weight) * elo + fifa_weight * fifa_elo
    if champion_prob is not None and champion_weight > 0:
        market_elo = champion_probability_to_elo(champion_prob, field_size=champion_field_size)
        return (1.0 - champion_weight) * base + champion_weight * market_elo
    return base
