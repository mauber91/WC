from __future__ import annotations

import csv
import hashlib
import io
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from world_cup_api.config import ROOT_DIR
from world_cup_api.db.models import (
    BookmakerOdds, Group, IngestionRun, Match, PlayerInjury, PredictionMarketPrice, SquadPlayer, Team,
    TeamRating, Tournament,
)
from world_cup_api.services.results import revise_result


REQUIRED = {
    "teams": {"fifa_code", "name", "country_code", "confederation"},
    "fixtures": {"match_number", "group_code", "team_a_fifa_code", "team_b_fifa_code", "scheduled_at"},
    "results": {"match_number", "team_a_goals_90", "team_b_goals_90"},
    "ratings": {"fifa_code", "rating_type", "rating_value", "effective_at", "source"},
    "bookmaker_odds": {"match_number", "bookmaker", "selection", "decimal_odds", "snapshot_at"},
    "prediction_markets": {"platform", "external_market_id", "contract_id", "market_type", "selection", "yes_price", "snapshot_at"},
    "squad": {"fifa_code", "name", "position", "squad_number", "fc26_overall", "market_value_meur"},
    "player_injuries": {"fifa_code", "player_name", "started_on", "days_out"},
}


def preview_import(db: Session, dataset: str, content: bytes, source: str) -> tuple[IngestionRun, list[dict], list[dict]]:
    if dataset not in REQUIRED:
        raise ValueError(f"Unsupported dataset: {dataset}")
    checksum = hashlib.sha256(content).hexdigest()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    missing = sorted(REQUIRED[dataset] - set(reader.fieldnames or []))
    rows = list(reader)
    errors = [{"row": 1, "message": f"Missing columns: {', '.join(missing)}"}] if missing else []
    for index, row in enumerate(rows, start=2):
        if any(row.get(column, "").strip() == "" for column in REQUIRED[dataset]):
            errors.append({"row": index, "message": "One or more required values are empty"})
    run_id = str(uuid.uuid4())
    staging = ROOT_DIR / "data" / "app" / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    path = staging / f"{run_id}.csv"
    path.write_bytes(content)
    run = IngestionRun(id=run_id, dataset_type=dataset, source=source, status="invalid" if errors else "validated",
                       checksum=checksum, staged_path=str(path), record_count=len(rows), error_count=len(errors),
                       error_json=errors or None)
    db.add(run)
    db.commit()
    db.refresh(run)
    return run, rows[:20], errors


def commit_import(db: Session, run_id: str) -> IngestionRun:
    run = db.get(IngestionRun, run_id)
    if run is None or run.status != "validated" or not run.staged_path:
        raise ValueError("A validated import preview is required")
    with Path(run.staged_path).open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    handlers = {
        "teams": _teams, "fixtures": _fixtures, "results": _results, "ratings": _ratings,
        "bookmaker_odds": _odds, "prediction_markets": _markets, "squad": _squad,
        "player_injuries": _player_injuries,
    }
    try:
        handlers[run.dataset_type](db, rows, run.source)
        run.status = "committed"
        run.completed_at = datetime.now(timezone.utc)
        run.source_cutoff_at = run.completed_at
        db.commit()
    except Exception as exc:
        db.rollback()
        run = db.get(IngestionRun, run_id)
        assert run is not None
        run.status = "failed"
        run.error_count = 1
        run.error_json = [{"message": str(exc)}]
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        raise
    Path(run.staged_path).unlink(missing_ok=True)
    return run


def _teams(db: Session, rows: list[dict], _source: str) -> None:
    for row in rows:
        team = db.scalar(select(Team).where(Team.fifa_code == row["fifa_code"].upper())) or Team(fifa_code=row["fifa_code"].upper())
        team.name = row["name"]
        team.short_name = row.get("short_name") or row["name"]
        team.country_code = row["country_code"].upper()
        team.confederation = row["confederation"].upper()
        db.add(team)


def _fixtures(db: Session, rows: list[dict], _source: str) -> None:
    tournament = db.scalar(select(Tournament).where(Tournament.code == "FWC2026"))
    assert tournament
    for row in rows:
        number = int(row["match_number"])
        match = db.scalar(select(Match).where(Match.tournament_id == tournament.id, Match.official_match_number == number))
        group = db.scalar(select(Group).where(Group.tournament_id == tournament.id, Group.code == row["group_code"].upper()))
        team_a = db.scalar(select(Team).where(Team.fifa_code == row["team_a_fifa_code"].upper()))
        team_b = db.scalar(select(Team).where(Team.fifa_code == row["team_b_fifa_code"].upper()))
        if not group or not team_a or not team_b:
            raise ValueError(f"Unknown group/team reference for match {number}")
        if not match:
            match = Match(tournament_id=tournament.id, official_match_number=number, stage="group")
        match.group_id, match.team_a_id, match.team_b_id = group.id, team_a.id, team_b.id
        match.scheduled_at = datetime.fromisoformat(row["scheduled_at"].replace("Z", "+00:00"))
        match.venue = row.get("venue") or "TBD"
        match.host_country = row.get("host_country") or "US"
        match.status = row.get("status") or "scheduled"
        db.add(match)


def _results(db: Session, rows: list[dict], source: str) -> None:
    for row in rows:
        match = db.scalar(select(Match).where(Match.official_match_number == int(row["match_number"])))
        if not match:
            raise ValueError(f"Unknown match {row['match_number']}")
        payload = {"team_a_goals_90": int(row["team_a_goals_90"]), "team_b_goals_90": int(row["team_b_goals_90"]), "source": source}
        for field in ("team_a_yellows", "team_b_yellows", "team_a_indirect_reds", "team_b_indirect_reds", "team_a_direct_reds", "team_b_direct_reds", "team_a_yellow_direct_reds", "team_b_yellow_direct_reds"):
            payload[field] = int(row[field]) if row.get(field) else None
        revise_result(db, match.id, payload)


def _ratings(db: Session, rows: list[dict], source: str) -> None:
    for row in rows:
        team = db.scalar(select(Team).where(Team.fifa_code == row["fifa_code"].upper()))
        if not team:
            raise ValueError(f"Unknown team {row['fifa_code']}")
        value = float(row["rating_value"])
        db.add(TeamRating(team_id=team.id, rating_type=row["rating_type"].upper(), rating_value=value,
                          rank=int(row["rank"]) if row.get("rank") else None,
                          effective_at=datetime.fromisoformat(row["effective_at"].replace("Z", "+00:00")), source=source))


def _odds(db: Session, rows: list[dict], _source: str) -> None:
    for row in rows:
        match = db.scalar(select(Match).where(Match.official_match_number == int(row["match_number"])))
        if not match:
            raise ValueError(f"Unknown match {row['match_number']}")
        db.add(BookmakerOdds(match_id=match.id, bookmaker=row["bookmaker"], market_type=row.get("market_type") or "1X2",
                             selection=row["selection"], line_value=float(row.get("line_value") or 0),
                             decimal_odds=float(row["decimal_odds"]),
                             snapshot_at=datetime.fromisoformat(row["snapshot_at"].replace("Z", "+00:00"))))


def _markets(db: Session, rows: list[dict], _source: str) -> None:
    for row in rows:
        match = db.scalar(select(Match).where(Match.official_match_number == int(row["match_number"]))) if row.get("match_number") else None
        db.add(PredictionMarketPrice(platform=row["platform"], external_market_id=row["external_market_id"],
                                     contract_id=row["contract_id"], market_type=row["market_type"],
                                     match_id=match.id if match else None, selection=row["selection"],
                                     yes_price=float(row["yes_price"]),
                                     best_bid=float(row["best_bid"]) if row.get("best_bid") else None,
                                     best_ask=float(row["best_ask"]) if row.get("best_ask") else None,
                                     volume=float(row["volume"]) if row.get("volume") else None,
                                     snapshot_at=datetime.fromisoformat(row["snapshot_at"].replace("Z", "+00:00"))))


def _squad(db: Session, rows: list[dict], _source: str) -> None:
    for row in rows:
        team = db.scalar(select(Team).where(Team.fifa_code == row["fifa_code"].upper()))
        if not team:
            raise ValueError(f"Unknown team {row['fifa_code']}")
        player = db.scalar(
            select(SquadPlayer).where(
                SquadPlayer.team_id == team.id,
                SquadPlayer.squad_number == int(row["squad_number"]),
            )
        ) or SquadPlayer(team_id=team.id, squad_number=int(row["squad_number"]))
        player.name = row["name"]
        player.position = row["position"].upper()
        player.fc26_overall = int(row["fc26_overall"])
        player.market_value_meur = float(row["market_value_meur"])
        player.season_rating_2025_26 = float(row["season_rating_2025_26"]) if row.get("season_rating_2025_26") else None
        player.season_rating_2024_25 = float(row["season_rating_2024_25"]) if row.get("season_rating_2024_25") else None
        player.season_rating_2023_24 = float(row["season_rating_2023_24"]) if row.get("season_rating_2023_24") else None
        db.add(player)


def _player_injuries(db: Session, rows: list[dict], _source: str) -> None:
    from datetime import date as date_type

    for row in rows:
        team = db.scalar(select(Team).where(Team.fifa_code == row["fifa_code"].upper()))
        if not team:
            raise ValueError(f"Unknown team {row['fifa_code']}")
        player = db.scalar(
            select(SquadPlayer).where(SquadPlayer.team_id == team.id, SquadPlayer.name == row["player_name"])
        )
        if not player:
            raise ValueError(f"Unknown player {row['player_name']} for {row['fifa_code']}")
        started = date_type.fromisoformat(row["started_on"])
        ended = date_type.fromisoformat(row["ended_on"]) if row.get("ended_on") else None
        db.add(PlayerInjury(
            player_id=player.id,
            started_on=started,
            ended_on=ended,
            days_out=int(row["days_out"]),
        ))
