from world_cup_api.modeling.context_params import rest_curve, travel_curve
from world_cup_api.modeling.prediction import expected_goals


def test_rest_and_travel_shift_lambdas_in_expected_direction() -> None:
    base_a, base_b = expected_goals(1700, 1700)
    rested_a, tired_b = expected_goals(1700, 1700, rest_a=4, rest_b=1, travel_a=500, travel_b=3000)
    assert rested_a > base_a
    assert tired_b < base_b


def test_curves_saturate() -> None:
    assert rest_curve(10) == 1.0
    assert travel_curve(5000) == 1.0
