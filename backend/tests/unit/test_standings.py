from world_cup_api.domain.standings import MatchRecord, StandingRow, calculate_group_table, rank_third_place


def rows() -> list[StandingRow]:
    return [StandingRow(team_id=i, name=str(i), fifa_rank_history=(i,)) for i in range(1, 5)]


def test_head_to_head_precedes_overall_goal_difference() -> None:
    table = calculate_group_table(rows(), [
        MatchRecord(1, 2, 1, 0, -1, -1),
        MatchRecord(1, 3, 0, 4, -1, -1),
        MatchRecord(1, 4, 1, 0, -1, -1),
        MatchRecord(2, 3, 1, 0, -1, -1),
        MatchRecord(2, 4, 1, 0, -1, -1),
        MatchRecord(3, 4, 0, 0, -1, -1),
    ])
    assert [row.team_id for row in table.rows[:2]] == [1, 2]
    assert table.rows[0].goal_difference < table.rows[1].goal_difference


def test_missing_conduct_uses_ranking_and_marks_provisional() -> None:
    candidates = rows()[:2]
    for candidate in candidates:
        candidate.conduct_score = None
    table = calculate_group_table(candidates, [])
    assert [row.team_id for row in table.rows] == [1, 2]
    assert table.provisional


def test_third_place_ranking_uses_points_then_goal_difference() -> None:
    candidates = rows()
    candidates[0].points, candidates[0].goals_for, candidates[0].goals_against = 4, 3, 3
    candidates[1].points, candidates[1].goals_for, candidates[1].goals_against = 4, 4, 3
    candidates[2].points = 3
    candidates[3].points = 2
    assert [row.team_id for row in rank_third_place(candidates).rows[:2]] == [2, 1]


def test_group_a_mexico_wins_head_to_head_when_level_on_six_points() -> None:
    """Mexico beat Korea 1-0; a final-day 6-6 tie must still leave Mexico first."""
    mexico = StandingRow(team_id=1, name="Mexico", fifa_rank_history=(14,))
    korea = StandingRow(team_id=2, name="Korea Republic", fifa_rank_history=(25,))
    czechia = StandingRow(team_id=3, name="Czechia", fifa_rank_history=(40,))
    south_africa = StandingRow(team_id=4, name="South Africa", fifa_rank_history=(60,))
    records = [
        MatchRecord(1, 4, 2, 0, -2, -5),   # M1
        MatchRecord(2, 3, 2, 1, -2, -2),   # M2
        MatchRecord(3, 4, 1, 1, -2, -2),   # M25
        MatchRecord(1, 2, 1, 0, -2, -2),   # M28 direct matchup
        MatchRecord(3, 1, 1, 0, -2, -2),   # M53 Czechia beat Mexico
        MatchRecord(2, 4, 1, 0, -2, -2),   # M54 Korea beat South Africa
    ]
    table = calculate_group_table([mexico, korea, czechia, south_africa], records)
    assert [row.name for row in table.rows] == [
        "Mexico",
        "Korea Republic",
        "Czechia",
        "South Africa",
    ]
    assert table.rows[0].points == table.rows[1].points == 6
