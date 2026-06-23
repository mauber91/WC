import numpy as np
import pytest

from world_cup_api.modeling.context_params import DEFAULT_CONTEXT_PARAMS
from world_cup_api.modeling.prediction import (
    build_forecast,
    devig,
    nbinom_marginal_pmf,
    one_x_two,
    poisson_score_matrix,
    score_matrix,
)


def test_devig_normalizes_three_way_market() -> None:
    probabilities = devig([2.0, 3.5, 4.0])
    assert sum(probabilities) == pytest.approx(1.0)
    assert probabilities[0] > probabilities[1] > probabilities[2]


def test_score_matrix_matches_blended_marginals() -> None:
    forecast = build_forecast(1800, 1600, (0.6, 0.25, 0.15))
    assert one_x_two(np.asarray(forecast.score_matrix)) == pytest.approx(forecast.final, abs=1e-10)


def test_zero_dispersion_matches_poisson() -> None:
    poisson = poisson_score_matrix(1.4, 1.1)
    neutral = score_matrix(1.4, 1.1, goal_dispersion=0.0)
    assert neutral == pytest.approx(poisson, abs=1e-12)


def test_negative_binomial_adds_tail_mass() -> None:
    mu = 1.35
    poisson = nbinom_marginal_pmf(mu, 0.0, 10)
    dispersed = nbinom_marginal_pmf(mu, DEFAULT_CONTEXT_PARAMS.goal_dispersion, 10)
    assert dispersed[0] > poisson[0]
    assert sum(dispersed[4:]) > sum(poisson[4:])


def test_build_forecast_with_dispersion_still_normalizes() -> None:
    forecast = build_forecast(
        1800,
        1600,
        (0.6, 0.25, 0.15),
        goal_dispersion=DEFAULT_CONTEXT_PARAMS.goal_dispersion,
    )
    matrix = np.asarray(forecast.score_matrix)
    assert matrix.sum() == pytest.approx(1.0)
    assert one_x_two(matrix) == pytest.approx(forecast.final, abs=1e-10)


def test_m52_fused_strength_favors_bosnia() -> None:
    from world_cup_api.domain.team_strength import fuse_strength
    from world_cup_api.modeling.context_params import DEFAULT_CONTEXT_PARAMS

    w = DEFAULT_CONTEXT_PARAMS.fifa_strength_weight
    forecast = build_forecast(
        fuse_strength(1596, 64, fifa_weight=w),
        fuse_strength(1437, 56, fifa_weight=w),
        market_blend_alpha=0.0,
    )
    assert forecast.model[0] > forecast.model[2]
