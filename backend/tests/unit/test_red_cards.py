from world_cup_api.domain.red_cards import OPPONENT_RED_GOAL_EQUIV, adjust_goals_for_red_cards


def test_canada_qatar_six_nil_with_two_opponent_reds() -> None:
    # Canada 6–0 Qatar; Qatar finished with two direct reds (M27 seed).
    assert adjust_goals_for_red_cards(6, 0, reds_a=0, reds_b=2) == (4, 0)


def test_no_reds_leaves_score_unchanged() -> None:
    assert adjust_goals_for_red_cards(2, 1, reds_a=0, reds_b=0) == (2, 1)


def test_opponent_red_cannot_flip_winner() -> None:
    # 2–1 with one opponent red → 1–1 effective table score, still a draw for sim GD.
    assert adjust_goals_for_red_cards(2, 1, reds_a=0, reds_b=1) == (1, 1)


def test_winner_reds_on_losing_side_do_not_adjust() -> None:
    assert adjust_goals_for_red_cards(0, 3, reds_a=2, reds_b=0) == (0, 1)


def test_draw_unaffected_by_reds() -> None:
    assert adjust_goals_for_red_cards(1, 1, reds_a=1, reds_b=2) == (1, 1)


def test_default_equiv_constant() -> None:
    assert OPPONENT_RED_GOAL_EQUIV == 0.8
