from world_cup_api.services.seed import seed_database
from world_cup_api.simulation.engine import build_input_snapshot, run_trials


def test_mexico_always_wins_group_a_after_two_wins(db_session) -> None:
    seed_database(db_session)
    snapshot, _ = build_input_snapshot(db_session)
    output = run_trials(snapshot, iterations=5000, seed=2026)
    mexico_id = next(
        team["id"]
        for group in snapshot["groups"].values()
        for team in group["teams"]
        if team["name"] == "Mexico"
    )
    counts = output["teams"][mexico_id]
    completed = output["completed"]
    assert counts["finish_1"] == completed
    assert counts["finish_2"] == 0


def test_korea_can_finish_third_in_group_a_with_locked_results(db_session) -> None:
    seed_database(db_session)
    snapshot, _ = build_input_snapshot(db_session)
    output = run_trials(snapshot, iterations=10_000, seed=2026)
    korea_id = next(
        team["id"]
        for group in snapshot["groups"].values()
        for team in group["teams"]
        if team["name"] == "Korea Republic"
    )
    counts = output["teams"][korea_id]
    completed = output["completed"]
    assert counts["finish_2"] > 0
    assert counts["finish_3"] > 0
    assert counts["finish_2"] + counts["finish_3"] + counts["finish_4"] == completed
    assert counts["finish_2"] / completed > 0.75
    assert counts["finish_3"] / completed > 0.05
