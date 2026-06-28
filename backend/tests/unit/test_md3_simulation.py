from world_cup_api.services.seed import seed_database
from world_cup_api.simulation.engine import build_input_snapshot, run_trials


def test_locked_group_a_skips_stochastic_matchday_three_paths(db_session) -> None:
    """Seed data now locks all six Group A fixtures, so finishes are deterministic."""
    seed_database(db_session)
    snapshot, _ = build_input_snapshot(db_session)
    group_a = next(group for group in snapshot["groups"].values() if any(team["name"] == "Mexico" for team in group["teams"]))
    korea_id = next(team["id"] for team in group_a["teams"] if team["name"] == "Korea Republic")
    open_md3 = [
        match
        for match in group_a["matches"]
        if match.get("matchday") == 3 and "completed" not in match
    ]

    assert open_md3 == []
    output = run_trials(snapshot, iterations=5_000, seed=2026)
    counts = output["teams"][korea_id]
    completed = output["completed"]

    assert counts["finish_3"] == completed
    assert counts["finish_2"] == 0
