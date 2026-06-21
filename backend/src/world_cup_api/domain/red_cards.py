from __future__ import annotations

# Each opponent red card reduces the winner's effective margin by this many goals
# when building simulation group tables (official FIFA scores stay unchanged).
OPPONENT_RED_GOAL_EQUIV = 0.8


def red_card_total(
    indirect: int | None,
    direct: int | None,
    yellow_direct: int | None,
) -> int:
    return int(indirect or 0) + int(direct or 0) + int(yellow_direct or 0)


def adjust_goals_for_red_cards(
    goals_a: int,
    goals_b: int,
    reds_a: int,
    reds_b: int,
    *,
    opponent_red_goal_equiv: float = OPPONENT_RED_GOAL_EQUIV,
) -> tuple[int, int]:
    """Return goals adjusted for numerical advantage from opponent red cards.

    Used only inside Monte Carlo group standings. Official match records are not
    modified. When the opponent finished with red card(s), shrink the winner's
    margin by up to ``opponent_red_goal_equiv`` goals per red.
    """
    adj_a, adj_b = goals_a, goals_b
    if goals_a > goals_b and reds_b > 0:
        cut = min(goals_a - goals_b, int(round(opponent_red_goal_equiv * reds_b)))
        adj_a -= cut
    elif goals_b > goals_a and reds_a > 0:
        cut = min(goals_b - goals_a, int(round(opponent_red_goal_equiv * reds_a)))
        adj_b -= cut
    return adj_a, adj_b
