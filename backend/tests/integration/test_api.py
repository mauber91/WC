import csv

from fastapi.testclient import TestClient
import pytest

from world_cup_api.config import ROOT_DIR
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


def test_batch_prediction_contract() -> None:
    with TestClient(app) as client:
        matches = client.get("/api/v1/matches").json()[:3]
        params = [("match_ids", match["id"]) for match in matches]
        response = client.get("/api/v1/matches/predictions", params=params)
        assert response.status_code == 200
        payload = response.json()
        assert set(payload) == {str(match["id"]) for match in matches}
        assert all(sum(row["final"].values()) == pytest.approx(1.0) for row in payload.values())


def _seeded_upcoming_market_fixture() -> tuple[int, set[str], set[str]]:
    seed_dir = ROOT_DIR / "data" / "seed"
    with (seed_dir / "results.csv").open(newline="", encoding="utf-8-sig") as handle:
        completed = {int(row["match_number"]) for row in csv.DictReader(handle)}
    bookmakers: dict[int, set[str]] = {}
    with (seed_dir / "bookmaker_odds.csv").open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            bookmakers.setdefault(int(row["match_number"]), set()).add(row["bookmaker"])
    platforms: dict[int, set[str]] = {}
    with (seed_dir / "prediction_markets.csv").open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            platforms.setdefault(int(row["match_number"]), set()).add(row["platform"])
    match_number = min((set(bookmakers) & set(platforms)) - completed)
    return match_number, bookmakers[match_number], platforms[match_number]


def test_upcoming_match_uses_seeded_market_odds() -> None:
    match_number, expected_bookmakers, expected_platforms = _seeded_upcoming_market_fixture()
    with TestClient(app) as client:
        matches = client.get("/api/v1/matches").json()
        upcoming = next(
            row for row in matches if row["official_match_number"] == match_number and row["result"] is None
        )
        response = client.get(f"/api/v1/matches/{upcoming['id']}/prediction")
        assert response.status_code == 200
        payload = response.json()
        assert payload["market"] is not None
        assert payload["data_quality"] == "market_blend"
        assert len(payload["market_sources"]) >= 2
        assert expected_bookmakers <= {
            source["bookmaker"] for source in payload["market_sources"] if source.get("bookmaker")
        }
        assert expected_platforms <= {
            source["platform"] for source in payload["market_sources"] if source.get("platform")
        }
