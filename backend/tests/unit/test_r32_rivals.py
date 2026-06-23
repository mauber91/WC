from world_cup_api.services.seed import seed_database
from world_cup_api.simulation.engine import build_input_snapshot, run_trials


def test_r32_rivals_are_recorded_per_group_finish(db_session) -> None:
    seed_database(db_session)
    snapshot, _ = build_input_snapshot(db_session)
    netherlands_id = next(
        int(team_id)
        for team_id, team in snapshot["teams"].items()
        if team["name"] == "Netherlands"
    )
    output = run_trials(snapshot, iterations=5_000, seed=2026)
    counts = output["teams"][netherlands_id]
    rivals_by_position: dict[int, dict[int, int]] = {1: {}, 2: {}, 3: {}}
    for (team_id, finish_position, opponent_id), count in output["r32_rivals"].items():
        if team_id == netherlands_id:
            rivals_by_position[finish_position][opponent_id] = count

    assert counts["finish_1"] > 0
    assert sum(rivals_by_position[1].values()) == counts["finish_1"]
    assert sum(rivals_by_position[2].values()) == counts["finish_2"]
    assert sum(rivals_by_position[3].values()) <= counts["finish_3"]
    assert all(
        opponent_id != netherlands_id
        for bucket in rivals_by_position.values()
        for opponent_id in bucket
    )
