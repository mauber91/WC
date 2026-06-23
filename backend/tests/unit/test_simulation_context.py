import numpy as np

from world_cup_api.domain.group_situation import (
    TeamGroupSituation,
    apply_collusion_draw_boost,
    mutual_draw_incentive,
    rotation_elo_penalty,
    should_rotate_team,
)
from world_cup_api.modeling.context_params import DEFAULT_CONTEXT_PARAMS
from world_cup_api.modeling.prediction import one_x_two
from world_cup_api.simulation.engine import _simulate_group_match


def _params() -> dict[str, float | int]:
    params = DEFAULT_CONTEXT_PARAMS
    return {
        "rotation_elo_locked_first": params.rotation_elo_locked_first,
        "rotation_elo_clinched": params.rotation_elo_clinched,
        "rotation_elo_eliminated": params.rotation_elo_eliminated,
        "collusion_draw_boost": params.collusion_draw_boost,
    }


def _situation(**kwargs: object) -> TeamGroupSituation:
    defaults = {
        "team_id": 1,
        "min_position": 1,
        "max_position": 4,
        "reachable_positions": frozenset({1, 2, 3, 4}),
        "position_locked": False,
        "locked_position": None,
        "can_qualify_top_two": True,
        "can_miss_top_two": True,
        "qualifies_with_win": True,
        "qualifies_with_draw": True,
        "qualifies_with_loss": False,
        "eliminated_with_loss": True,
    }
    defaults.update(kwargs)
    return TeamGroupSituation(**defaults)  # type: ignore[arg-type]


def test_rotation_penalty_for_locked_first_and_eliminated() -> None:
    params = _params()
    locked_first = _situation(position_locked=True, locked_position=1, reachable_positions=frozenset({1}))
    locked_last = _situation(
        team_id=4,
        position_locked=True,
        locked_position=4,
        reachable_positions=frozenset({4}),
        can_qualify_top_two=False,
    )
    still_fighting = _situation(min_position=1, max_position=2, can_miss_top_two=True)

    assert rotation_elo_penalty(locked_first, params) == params["rotation_elo_locked_first"]
    assert rotation_elo_penalty(locked_last, params) == params["rotation_elo_eliminated"]
    assert rotation_elo_penalty(still_fighting, params) == 0.0
    assert should_rotate_team(locked_first, params)
    assert not should_rotate_team(still_fighting, params)


def test_mutual_draw_incentive_requires_both_sides() -> None:
    collusion = _situation(team_id=1)
    partner = _situation(team_id=2)
    selfish = _situation(team_id=3, qualifies_with_draw=False, eliminated_with_loss=True)

    assert mutual_draw_incentive(collusion, partner)
    assert not mutual_draw_incentive(collusion, selfish)


def test_collusion_draw_boost_increases_draw_probability() -> None:
    matrix = np.array([
        [0.10, 0.10, 0.05],
        [0.10, 0.20, 0.10],
        [0.05, 0.10, 0.20],
    ])
    base_draw = one_x_two(matrix)[1]
    boosted = apply_collusion_draw_boost(matrix, 0.18)
    assert one_x_two(boosted)[1] > base_draw


def test_simulate_group_match_applies_draw_boost() -> None:
    matrix = np.array([[0.4, 0.2], [0.2, 0.2]])
    match = {"a": 1, "b": 2, "forecast": {"matrix": matrix.tolist()}}
    rng = np.random.default_rng(0)

    draws = 0
    for _ in range(5000):
        ga, gb, _, _ = _simulate_group_match(match, rng, draw_boost=0.35)
        if ga == gb:
            draws += 1
    assert draws / 5000 > 0.35


def test_rotation_variant_matrix_is_used() -> None:
    matrix = np.array([[0.25, 0.25], [0.25, 0.25]])
    match = {
        "a": 1,
        "b": 2,
        "rotation_variants": {
            "00": {"matrix": matrix.tolist()},
            "10": {"matrix": matrix.tolist()},
        },
    }
    goals_a, goals_b, _, _ = _simulate_group_match(match, np.random.default_rng(0), rot_a=True, rot_b=False)
    assert goals_a in (0, 1)
    assert goals_b in (0, 1)
