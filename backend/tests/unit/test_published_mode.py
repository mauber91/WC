from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from world_cup_api.config import get_settings
from world_cup_api.db.models import Simulation, Tournament
from world_cup_api.db.session import SessionLocal
from world_cup_api.main import app


@pytest.fixture(autouse=True)
def reset_settings() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_simulations_post_disabled_when_flag_off() -> None:
    os.environ["WC_SIMULATIONS_ENABLED"] = "false"
    get_settings.cache_clear()
    with TestClient(app) as client:
        response = client.post("/api/v1/simulations", json={"iterations": 10000, "seed": 2026})
    assert response.status_code == 403


def test_published_simulation_id_restricts_access() -> None:
    cutoff = datetime(2026, 6, 20, tzinfo=timezone.utc)
    with SessionLocal() as db:
        tournament = db.query(Tournament).first()
        assert tournament is not None
        db.add_all([
            Simulation(
                id="published-run",
                tournament_id=tournament.id,
                status="completed",
                iterations=10000,
                progress_iterations=10000,
                seed=2026,
                input_cutoff_at=cutoff,
                input_hash="abc",
                input_snapshot_json={},
                ruleset_version="rules-v1",
            ),
            Simulation(
                id="other-run",
                tournament_id=tournament.id,
                status="completed",
                iterations=10000,
                progress_iterations=10000,
                seed=2026,
                input_cutoff_at=cutoff,
                input_hash="def",
                input_snapshot_json={},
                ruleset_version="rules-v1",
            ),
        ])
        db.commit()

    os.environ["WC_PUBLISHED_SIMULATION_ID"] = "published-run"
    get_settings.cache_clear()
    with TestClient(app) as client:
        listed = client.get("/api/v1/simulations")
        assert listed.status_code == 200
        assert [row["id"] for row in listed.json()] == ["published-run"]

        allowed = client.get("/api/v1/simulations/published-run")
        blocked = client.get("/api/v1/simulations/other-run")
        assert allowed.status_code == 200
        assert blocked.status_code == 404

        published_meta = client.get("/api/v1/published")
        assert published_meta.status_code == 200
        assert published_meta.json()["simulation_id"] == "published-run"

    with SessionLocal() as db:
        db.query(Simulation).filter(Simulation.id.in_(["published-run", "other-run"])).delete()
        db.commit()
