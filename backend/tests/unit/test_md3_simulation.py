from world_cup_api.services.seed import seed_database
from world_cup_api.simulation.engine import build_input_snapshot, run_trials


def test_group_a_korea_still_has_third_place_paths_after_md3_model(db_session) -> None:
    seed_database(db_session)
    snapshot, _ = build_input_snapshot(db_session)
    korea_id = next(
        team["id"]
        for group in snapshot["groups"].values()
        for team in group["teams"]
        if team["name"] == "Korea Republic"
    )
    output = run_trials(snapshot, iterations=5_000, seed=2026)
    counts = output["teams"][korea_id]
    completed = output["completed"]

    assert counts["finish_3"] > 0
    assert counts["finish_2"] > counts["finish_3"]
    assert counts["finish_2"] + counts["finish_3"] + counts["finish_4"] == completed
