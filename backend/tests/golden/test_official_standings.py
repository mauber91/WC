from __future__ import annotations

import csv
import json

import pytest
from fastapi.testclient import TestClient

from world_cup_api.config import ROOT_DIR
from world_cup_api.domain.standings import MatchRecord, StandingRow, calculate_group_table
from world_cup_api.main import app


SEED_DIR = ROOT_DIR / "data" / "seed"
SNAPSHOT_PATH = SEED_DIR / "standings_snapshot_june20.json"


def _load_snapshot() -> dict:
    return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))


def _fixture_rows() -> dict[int, tuple[str, str, str]]:
    fixtures: dict[int, tuple[str, str, str]] = {}
    with (SEED_DIR / "fixtures.csv").open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            fixtures[int(row["match_number"])] = (
                row["group_code"].upper(),
                row["team_a_fifa_code"].upper(),
                row["team_b_fifa_code"].upper(),
            )
    return fixtures


def _conduct_score(row: dict[str, str], prefix: str) -> int:
    values = [int(row[f"{prefix}_{suffix}"]) for suffix in (
        "yellows", "indirect_reds", "direct_reds", "yellow_direct_reds",
    )]
    return -(values[0] + 3 * values[1] + 4 * values[2] + 5 * values[3])


def _result_rows() -> dict[int, dict[str, str]]:
    results: dict[int, dict[str, str]] = {}
    with (SEED_DIR / "results.csv").open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            results[int(row["match_number"])] = row
    return results


def _group_members() -> dict[str, list[str]]:
    members: dict[str, list[str]] = {}
    with (SEED_DIR / "draw.csv").open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            code = row["group_code"].upper()
            members.setdefault(code, []).append(row["fifa_code"].upper())
    return members


def _fifa_ranks() -> dict[str, tuple[int, ...]]:
    ranks: dict[str, tuple[int, ...]] = {}
    with (SEED_DIR / "ratings.csv").open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            if row["rating_type"].upper() != "FIFA_RANK":
                continue
            ranks[row["fifa_code"].upper()] = (int(row["rank"]),)
    return ranks


def _compute_group_table(group_code: str) -> list[StandingRow]:
    members = _group_members()[group_code]
    ranks = _fifa_ranks()
    fixtures = _fixture_rows()
    results = _result_rows()
    team_ids = {code: index + 1 for index, code in enumerate(members)}
    rows = [
        StandingRow(team_id=team_ids[code], name=code, fifa_rank_history=ranks[code])
        for code in members
    ]
    records: list[MatchRecord] = []
    for match_number, (group, team_a, team_b) in fixtures.items():
        if group != group_code or match_number not in results:
            continue
        row = results[match_number]
        records.append(MatchRecord(
            team_ids[team_a], team_ids[team_b],
            int(row["team_a_goals_90"]), int(row["team_b_goals_90"]),
            _conduct_score(row, "team_a"), _conduct_score(row, "team_b"),
        ))
    return calculate_group_table(rows, records).rows


@pytest.mark.parametrize("group_code", list("ABCDEFGHIJKL"))
def test_seed_results_match_official_standings_snapshot(group_code: str) -> None:
    snapshot = _load_snapshot()["groups"][group_code]
    computed = {row.name: row for row in _compute_group_table(group_code)}
    for expected in snapshot:
        row = computed[expected["fifa_code"]]
        assert row.points == expected["points"]
        assert row.played == expected["played"]
        assert row.won == expected["won"]
        assert row.drawn == expected["drawn"]
        assert row.lost == expected["lost"]
        assert row.goals_for == expected["gf"]
        assert row.goals_against == expected["ga"]
        assert row.goal_difference == expected["gd"]


def _code_to_name() -> dict[str, str]:
    mapping: dict[str, str] = {}
    with (SEED_DIR / "draw.csv").open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            mapping[row["fifa_code"].upper()] = row["name"]
    return mapping


def test_seeded_api_standings_match_official_snapshot_for_completed_groups() -> None:
    snapshot = _load_snapshot()
    names = _code_to_name()
    with TestClient(app) as client:
        for group_code in ("A", "C", "D", "F"):
            response = client.get(f"/api/v1/groups/{group_code}/standings")
            assert response.status_code == 200
            payload = response.json()
            assert payload["provisional"] is False
            by_name = {row["name"]: row for row in payload["rows"]}
            for expected in snapshot["groups"][group_code]:
                row = by_name[names[expected["fifa_code"]]]
                assert row["points"] == expected["points"]
                assert row["goals_for"] == expected["gf"]
                assert row["goals_against"] == expected["ga"]
