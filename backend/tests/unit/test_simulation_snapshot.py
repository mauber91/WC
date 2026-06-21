import json

from world_cup_api.services.seed import seed_database
from world_cup_api.services.simulations import create_simulation
from world_cup_api.simulation.engine import build_input_snapshot


def test_build_input_snapshot_is_json_serializable(db_session) -> None:
    seed_database(db_session)
    snapshot, _ = build_input_snapshot(db_session)
    json.dumps(snapshot)


def test_create_simulation_persists_snapshot(db_session) -> None:
    seed_database(db_session)
    run = create_simulation(db_session, iterations=10000, seed=4242, force=True)
    assert run.status == "queued"
    json.dumps(run.input_snapshot_json)
