from world_cup_api.domain.group_situation import (
    Md3Fixture,
    analyze_group_before_matchday3,
    md3_fixtures_from_matches,
    mutual_draw_incentive,
    should_rotate_team,
)
from world_cup_api.domain.standings import MatchRecord, StandingRow


def _group_a_teams() -> list[StandingRow]:
    return [
        StandingRow(team_id=1, name="Mexico", fifa_rank_history=(14,)),
        StandingRow(team_id=2, name="Korea Republic", fifa_rank_history=(25,)),
        StandingRow(team_id=3, name="Czechia", fifa_rank_history=(40,)),
        StandingRow(team_id=4, name="South Africa", fifa_rank_history=(60,)),
    ]


def _group_a_early_records() -> list[MatchRecord]:
    return [
        MatchRecord(1, 4, 2, 0, -2, -5),   # M1 Mexico 2-0 South Africa
        MatchRecord(2, 3, 2, 1, -2, -2),   # M2 Korea 2-1 Czechia
        MatchRecord(3, 4, 1, 1, -2, -2),   # M25 Czechia 1-1 South Africa
        MatchRecord(1, 2, 1, 0, -2, -2),   # M28 Mexico 1-0 Korea
    ]


def _group_a_md3_fixtures() -> tuple[Md3Fixture, Md3Fixture]:
    return (
        Md3Fixture(team_a_id=3, team_b_id=1),  # Czechia vs Mexico
        Md3Fixture(team_a_id=4, team_b_id=2),  # South Africa vs Korea
    )


def test_mexico_locked_first_after_four_completed_group_a_matches() -> None:
    situation = analyze_group_before_matchday3(
        _group_a_teams(),
        _group_a_early_records(),
        _group_a_md3_fixtures(),
        detailed_scorelines=True,
    )
    mexico = situation.by_team_id()[1]

    assert mexico.position_locked
    assert mexico.locked_position == 1
    assert mexico.reachable_positions == frozenset({1})
    assert mexico.can_qualify_top_two
    assert not mexico.can_miss_top_two


def test_korea_not_locked_and_can_finish_second_third_or_fourth() -> None:
    situation = analyze_group_before_matchday3(
        _group_a_teams(),
        _group_a_early_records(),
        _group_a_md3_fixtures(),
        detailed_scorelines=True,
    )
    korea = situation.by_team_id()[2]

    assert not korea.position_locked
    assert korea.reachable_positions == frozenset({2, 3, 4})
    assert korea.can_qualify_top_two
    assert korea.can_miss_top_two
    assert korea.qualifies_with_win
    assert korea.qualifies_with_draw
    assert not korea.qualifies_with_loss
    assert korea.eliminated_with_loss


def test_south_africa_can_reach_second_on_final_day() -> None:
    situation = analyze_group_before_matchday3(
        _group_a_teams(),
        _group_a_early_records(),
        _group_a_md3_fixtures(),
        detailed_scorelines=True,
    )
    south_africa = situation.by_team_id()[4]

    assert south_africa.reachable_positions == frozenset({2, 3, 4})
    assert south_africa.qualifies_with_win
    assert not south_africa.qualifies_with_draw
    assert not south_africa.qualifies_with_loss


def test_open_group_before_final_day() -> None:
    teams = [
        StandingRow(team_id=1, name="A", fifa_rank_history=(10,)),
        StandingRow(team_id=2, name="B", fifa_rank_history=(20,)),
        StandingRow(team_id=3, name="C", fifa_rank_history=(30,)),
        StandingRow(team_id=4, name="D", fifa_rank_history=(40,)),
    ]
    early = [
        MatchRecord(1, 2, 1, 1, 0, 0),
        MatchRecord(3, 4, 1, 1, 0, 0),
        MatchRecord(1, 3, 1, 0, 0, 0),
        MatchRecord(2, 4, 0, 1, 0, 0),
    ]
    fixtures = (
        Md3Fixture(team_a_id=1, team_b_id=4),
        Md3Fixture(team_a_id=2, team_b_id=3),
    )
    situation = analyze_group_before_matchday3(teams, early, fixtures, detailed_scorelines=True)
    by_id = situation.by_team_id()

    assert not any(team.position_locked for team in situation.teams)
    assert by_id[1].reachable_positions == frozenset({1, 2, 3})
    assert by_id[4].reachable_positions == frozenset({1, 2, 3})
    assert by_id[2].can_qualify_top_two
    assert by_id[2].can_miss_top_two


def test_md3_fixtures_from_matches() -> None:
    matches = [
        {"id": 1, "a": 1, "b": 2, "matchday": 1, "scheduled_at": "2026-06-11T00:00:00Z"},
        {"id": 2, "a": 3, "b": 4, "matchday": 1, "scheduled_at": "2026-06-11T03:00:00Z"},
        {"id": 3, "a": 1, "b": 3, "matchday": 2, "scheduled_at": "2026-06-15T00:00:00Z"},
        {"id": 4, "a": 2, "b": 4, "matchday": 2, "scheduled_at": "2026-06-15T03:00:00Z"},
        {"id": 5, "a": 1, "b": 4, "matchday": 3, "scheduled_at": "2026-06-19T00:00:00Z"},
        {"id": 6, "a": 2, "b": 3, "matchday": 3, "scheduled_at": "2026-06-19T03:00:00Z"},
    ]
    fixtures = md3_fixtures_from_matches(matches)
    assert fixtures == (
        Md3Fixture(team_a_id=1, team_b_id=4),
        Md3Fixture(team_a_id=2, team_b_id=3),
    )


def test_group_a_mexico_rotates_korea_does_not_before_md3() -> None:
    from world_cup_api.modeling.context_params import DEFAULT_CONTEXT_PARAMS

    params = {
        "rotation_elo_locked_first": DEFAULT_CONTEXT_PARAMS.rotation_elo_locked_first,
        "rotation_elo_clinched": DEFAULT_CONTEXT_PARAMS.rotation_elo_clinched,
        "rotation_elo_eliminated": DEFAULT_CONTEXT_PARAMS.rotation_elo_eliminated,
    }
    situation = analyze_group_before_matchday3(
        _group_a_teams(),
        _group_a_early_records(),
        _group_a_md3_fixtures(),
        detailed_scorelines=True,
    )
    by_id = situation.by_team_id()

    assert should_rotate_team(by_id[1], params)
    assert not should_rotate_team(by_id[2], params)
    assert not mutual_draw_incentive(by_id[4], by_id[2])
