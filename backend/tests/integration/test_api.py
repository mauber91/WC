from fastapi.testclient import TestClient
import pytest

from world_cup_api.main import app


def test_team_detail_by_slug() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/teams/mexico")
        assert response.status_code == 200
        payload = response.json()
        assert payload["name"] == "Mexico"
        assert payload["slug"] == "mexico"
        assert payload["ratings"]["fifa_rank"] is not None
        assert payload["standing"]["points"] == 6
        assert len(payload["fixtures"]) == 3
        assert len(payload["squad"]) >= 20
        assert all(1 <= player["rating"] <= 99 for player in payload["squad"])

def test_team_squad_includes_real_players() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/teams/england")
        assert response.status_code == 200
        names = {player["name"] for player in response.json()["squad"]}
        assert "Jordan Pickford" in names or "Harry Kane" in names


def test_seeded_groups_and_standings_are_available() -> None:
    with TestClient(app) as client:
        groups = client.get("/api/v1/groups")
        assert groups.status_code == 200
        assert len(groups.json()) == 12
        standings = client.get("/api/v1/groups/A/standings")
        assert standings.status_code == 200
        assert len(standings.json()["rows"]) == 4
        assert standings.json()["provisional"] is False
        mexico = next(row for row in standings.json()["rows"] if row["name"] == "Mexico")
        assert mexico["points"] == 6


def test_prediction_contract() -> None:
    with TestClient(app) as client:
        match = client.get("/api/v1/matches").json()[0]
        response = client.get(f"/api/v1/matches/{match['id']}/prediction")
        assert response.status_code == 200
        assert sum(response.json()["final"].values()) == pytest.approx(1.0)


def test_upcoming_match_uses_seeded_market_odds() -> None:
    with TestClient(app) as client:
        matches = client.get("/api/v1/matches").json()
        germany_ivory = next(
            row for row in matches if row["official_match_number"] == 33 and row["result"] is None
        )
        response = client.get(f"/api/v1/matches/{germany_ivory['id']}/prediction")
        assert response.status_code == 200
        payload = response.json()
        assert payload["market"] is not None
        assert payload["data_quality"] == "complete"
        assert len(payload["market_sources"]) >= 2
        assert any(source.get("bookmaker") == "888sport" for source in payload["market_sources"])
        assert any(source.get("platform") == "polymarket" for source in payload["market_sources"])
