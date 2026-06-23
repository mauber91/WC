import numpy as np

from world_cup_api.modeling.evaluation import evaluate_probabilities


def test_evaluation_rewards_better_forecasts() -> None:
    actual = np.array([0, 1, 2])
    good = np.array([[0.8, 0.1, 0.1], [0.1, 0.8, 0.1], [0.1, 0.1, 0.8]])
    weak = np.full((3, 3), 1 / 3)
    assert evaluate_probabilities(actual, good).log_loss < evaluate_probabilities(actual, weak).log_loss
