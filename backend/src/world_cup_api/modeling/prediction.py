from __future__ import annotations

from dataclasses import dataclass
from math import exp, factorial, log

import numpy as np
from scipy.stats import nbinom


OUTCOMES = ("team_a", "draw", "team_b")


@dataclass(frozen=True)
class MatchForecast:
    lambda_a: float
    lambda_b: float
    model: tuple[float, float, float]
    market: tuple[float, float, float] | None
    final: tuple[float, float, float]
    score_matrix: tuple[tuple[float, ...], ...]


def devig(decimal_odds: list[float]) -> tuple[float, ...]:
    if not decimal_odds or any(value <= 1 for value in decimal_odds):
        raise ValueError("Decimal odds must all be greater than one")
    implied = [1 / value for value in decimal_odds]
    total = sum(implied)
    return tuple(value / total for value in implied)


def log_pool(vectors: list[tuple[float, ...]], weights: list[float]) -> tuple[float, ...]:
    if len(vectors) != len(weights) or not vectors:
        raise ValueError("Probability vectors and weights must be non-empty and aligned")
    if any(len(vector) != len(vectors[0]) for vector in vectors):
        raise ValueError("Probability vectors must have equal lengths")
    active = sum(weights)
    if active <= 0:
        raise ValueError("At least one weight must be positive")
    logits = [0.0] * len(vectors[0])
    for vector, weight in zip(vectors, weights, strict=True):
        for index, value in enumerate(vector):
            logits[index] += (weight / active) * log(max(value, 1e-12))
    values = [exp(value) for value in logits]
    total = sum(values)
    return tuple(value / total for value in values)


def expected_goals(
    elo_a: float,
    elo_b: float,
    host_a: bool = False,
    host_b: bool = False,
    rest_a: float = 0,
    rest_b: float = 0,
    travel_a: float = 0,
    travel_b: float = 0,
    *,
    beta_rest: float = 0.06,
    rest_cap: float = 4.0,
    beta_travel: float = 0.05,
    travel_ref: float = 3500.0,
) -> tuple[float, float]:
    from world_cup_api.modeling.context_params import rest_curve, travel_curve

    difference = 1.15 * (elo_a - elo_b) / 400
    host_delta = 0.13 * int(host_a) - 0.13 * int(host_b)
    rest_delta = beta_rest * (rest_curve(rest_a, cap=rest_cap) - rest_curve(rest_b, cap=rest_cap))
    travel_delta = beta_travel * (travel_curve(travel_b, ref=travel_ref) - travel_curve(travel_a, ref=travel_ref))
    baseline_log = log(1.32)
    total = difference / 2 + host_delta + rest_delta + travel_delta
    return (
        float(np.clip(exp(baseline_log + total), 0.15, 4.5)),
        float(np.clip(exp(baseline_log - total), 0.15, 4.5)),
    )


def poisson_score_matrix(lambda_a: float, lambda_b: float, max_goals: int = 10) -> np.ndarray:
    a = _poisson_marginal_pmf(lambda_a, max_goals)
    b = _poisson_marginal_pmf(lambda_b, max_goals)
    matrix = np.outer(a, b)
    return matrix / matrix.sum()


def _poisson_marginal_pmf(mu: float, max_goals: int) -> np.ndarray:
    pmf = np.array([exp(-mu) * mu**goal / factorial(goal) for goal in range(max_goals + 1)])
    pmf[-1] += max(0.0, 1.0 - pmf.sum())
    return pmf / pmf.sum()


def nbinom_marginal_params(mu: float, dispersion: float) -> tuple[float, float]:
    """Map mean/dispersion (Var = mu + dispersion * mu^2) to scipy nbinom(n, p)."""
    size = 1.0 / dispersion
    probability = size / (size + mu)
    return size, probability


def nbinom_marginal_pmf(mu: float, dispersion: float, max_goals: int = 10) -> np.ndarray:
    if dispersion <= 0:
        return _poisson_marginal_pmf(mu, max_goals)
    size, probability = nbinom_marginal_params(mu, dispersion)
    goals = np.arange(max_goals + 1)
    pmf = nbinom.pmf(goals, size, probability)
    pmf[-1] += max(0.0, 1.0 - pmf.sum())
    return pmf / pmf.sum()


def negative_binomial_score_matrix(
    lambda_a: float,
    lambda_b: float,
    dispersion: float,
    max_goals: int = 10,
) -> np.ndarray:
    a = nbinom_marginal_pmf(lambda_a, dispersion, max_goals)
    b = nbinom_marginal_pmf(lambda_b, dispersion, max_goals)
    matrix = np.outer(a, b)
    return matrix / matrix.sum()


def score_matrix(
    lambda_a: float,
    lambda_b: float,
    *,
    max_goals: int = 10,
    goal_dispersion: float = 0.0,
) -> np.ndarray:
    if goal_dispersion <= 0:
        return poisson_score_matrix(lambda_a, lambda_b, max_goals=max_goals)
    return negative_binomial_score_matrix(lambda_a, lambda_b, goal_dispersion, max_goals=max_goals)


def one_x_two(matrix: np.ndarray) -> tuple[float, float, float]:
    return float(np.tril(matrix, -1).sum()), float(np.trace(matrix)), float(np.triu(matrix, 1).sum())


def blend(
    model: tuple[float, ...],
    market: tuple[float, ...] | None,
    *,
    alpha: float = 0.85,
) -> tuple[float, ...]:
    if market is None:
        return model
    return log_pool([market, model], [alpha, 1 - alpha])


def reweight_score_matrix(matrix: np.ndarray, final: tuple[float, float, float]) -> np.ndarray:
    model = one_x_two(matrix)
    result = matrix.copy()
    masks = [np.tril(np.ones_like(matrix, dtype=bool), -1), np.eye(len(matrix), dtype=bool), np.triu(np.ones_like(matrix, dtype=bool), 1)]
    for target, source, mask in zip(final, model, masks, strict=True):
        result[mask] *= target / max(source, 1e-12)
    return result / result.sum()


def build_forecast(
    elo_a: float,
    elo_b: float,
    market: tuple[float, float, float] | None = None,
    host_a: bool = False,
    host_b: bool = False,
    rest_a: float = 0,
    rest_b: float = 0,
    travel_a: float = 0,
    travel_b: float = 0,
    *,
    beta_rest: float = 0.06,
    rest_cap: float = 4.0,
    beta_travel: float = 0.05,
    travel_ref: float = 3500.0,
    goal_dispersion: float = 0.0,
    market_blend_alpha: float = 0.85,
) -> MatchForecast:
    lambda_a, lambda_b = expected_goals(
        elo_a, elo_b, host_a=host_a, host_b=host_b,
        rest_a=rest_a, rest_b=rest_b, travel_a=travel_a, travel_b=travel_b,
        beta_rest=beta_rest, rest_cap=rest_cap, beta_travel=beta_travel, travel_ref=travel_ref,
    )
    raw_matrix = score_matrix(lambda_a, lambda_b, goal_dispersion=goal_dispersion)
    model = one_x_two(raw_matrix)
    final = blend(model, market, alpha=market_blend_alpha)
    matrix = reweight_score_matrix(raw_matrix, final)
    return MatchForecast(lambda_a, lambda_b, model, market, final, tuple(tuple(float(v) for v in row) for row in matrix))


def sample_score(forecast: MatchForecast, rng: np.random.Generator) -> tuple[int, int]:
    matrix = np.asarray(forecast.score_matrix)
    flat_index = int(rng.choice(matrix.size, p=matrix.ravel()))
    return divmod(flat_index, matrix.shape[1])


def knockout_winner(
    team_a_id: int,
    team_b_id: int,
    forecast: MatchForecast,
    rng: np.random.Generator,
) -> int:
    goals_a, goals_b = sample_score(forecast, rng)
    if goals_a != goals_b:
        return team_a_id if goals_a > goals_b else team_b_id
    extra_a = int(rng.poisson(forecast.lambda_a * 0.3))
    extra_b = int(rng.poisson(forecast.lambda_b * 0.3))
    if extra_a != extra_b:
        return team_a_id if extra_a > extra_b else team_b_id
    return team_a_id if rng.random() < 0.5 else team_b_id
