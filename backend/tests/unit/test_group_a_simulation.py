from world_cup_api.services.seed import seed_database
from world_cup_api.simulation.engine import build_input_snapshot, run_trials


def _group_a_team_ids(snapshot: dict) -> dict[str, int]:
    group = next(group for group in snapshot["groups"].values() if any(team["name"] == "Mexico" for team in group["teams"]))
    return {team["name"]: team["id"] for team in group["teams"]}


def test_mexico_wins_group_a_when_all_group_matches_are_locked(db_session) -> None:
    seed_database(db_session)
    snapshot, _ = build_input_snapshot(db_session)
    team_ids = _group_a_team_ids(snapshot)
    output = run_trials(snapshot, iterations=5000, seed=2026)
    completed = output["completed"]
    mexico = output["teams"][team_ids["Mexico"]]

    assert mexico["finish_1"] == completed
    assert mexico["finish_2"] == 0


def test_korea_finishes_third_when_all_group_a_matches_are_locked(db_session) -> None:
    seed_database(db_session)
    snapshot, _ = build_input_snapshot(db_session)
    team_ids = _group_a_team_ids(snapshot)
    output = run_trials(snapshot, iterations=10_000, seed=2026)
    completed = output["completed"]
    korea = output["teams"][team_ids["Korea Republic"]]
    south_africa = output["teams"][team_ids["South Africa"]]
    czechia = output["teams"][team_ids["Czechia"]]

    assert korea["finish_3"] == completed
    assert korea["finish_2"] == 0
    assert korea["finish_4"] == 0
    assert south_africa["finish_2"] == completed
    assert czechia["finish_4"] == completed
