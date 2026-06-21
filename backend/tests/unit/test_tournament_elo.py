from world_cup_api.domain.tournament_elo import build_elo_table, expected_score


def test_beaten_weaker_opponent_gains_less_than_beating_stronger_one() -> None:
    baseline = {1: 2115.0, 2: 1765.0, 3: 2024.0, 4: 1881.0}
    after_arg = build_elo_table(baseline, [(1, 2, 3, 0)])
    after_eng = build_elo_table(baseline, [(3, 4, 4, 2)])
    assert after_eng[3] - baseline[3] > after_arg[1] - baseline[1]


def test_england_closes_gap_on_argentina_after_openers() -> None:
    baseline = {1: 2115.0, 2: 1765.0, 3: 2024.0, 4: 1881.0}
    after_both = build_elo_table(baseline, [(1, 2, 3, 0), (3, 4, 4, 2)])
    gap_before = baseline[1] - baseline[3]
    gap_after = after_both[1] - after_both[3]
    assert gap_after < gap_before
    assert expected_score(after_both[1], after_both[3]) < expected_score(baseline[1], baseline[3])
