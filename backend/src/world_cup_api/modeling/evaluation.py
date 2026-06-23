from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np


@dataclass(frozen=True)
class EvaluationMetrics:
    log_loss: float
    brier_score: float
    ranked_probability_score: float
    expected_calibration_error: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


def evaluate_probabilities(actual: np.ndarray, probabilities: np.ndarray, bins: int = 10) -> EvaluationMetrics:
    """Evaluate ordered 1X2 forecasts without accepting future-data metadata."""
    actual = np.asarray(actual, dtype=int)
    probabilities = np.asarray(probabilities, dtype=float)
    if probabilities.ndim != 2 or probabilities.shape[1] != 3 or len(actual) != len(probabilities):
        raise ValueError("Expected N actual outcomes and an N x 3 probability matrix")
    if not np.allclose(probabilities.sum(axis=1), 1, atol=1e-8):
        raise ValueError("Each probability row must sum to one")
    one_hot = np.eye(3)[actual]
    clipped = np.clip(probabilities, 1e-12, 1)
    log_loss = float(-np.log(clipped[np.arange(len(actual)), actual]).mean())
    brier = float(np.square(probabilities - one_hot).sum(axis=1).mean())
    rps = float(np.square(np.cumsum(probabilities, axis=1)[:, :-1] - np.cumsum(one_hot, axis=1)[:, :-1]).sum(axis=1).mean() / 2)
    confidence = probabilities.max(axis=1)
    correct = probabilities.argmax(axis=1) == actual
    ece = 0.0
    for lower, upper in zip(np.linspace(0, 1, bins, endpoint=False), np.linspace(0, 1, bins + 1)[1:], strict=True):
        mask = (confidence >= lower) & (confidence <= upper if upper == 1 else confidence < upper)
        if mask.any():
            ece += float(mask.mean() * abs(correct[mask].mean() - confidence[mask].mean()))
    return EvaluationMetrics(log_loss, brier, rps, ece)
