from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from world_cup_api.config import ROOT_DIR, get_settings
from world_cup_api.db.models import PlayerInjury, SquadPlayer, Team
from world_cup_api.ingestion.api_football import (
    fetch_team_players,
    fetch_world_cup_teams,
    load_team_players_cached,
    match_season_rating,
    season_cache_path,
)
from world_cup_api.ingestion.ea_fc import load_ea_players, match_ea_overall
from world_cup_api.ingestion.transfermarkt import fetch_club, fetch_injuries, load_team_squad

SEED_DIR = ROOT_DIR / "data" / "seed"
EXTRACTION_STATUS_PATH = ROOT_DIR / "data" / "raw" / "api_football" / "extraction_status.json"


@dataclass(frozen=True)
class SeasonSpec:
    label: str
    api_year: int
    field: str


SEASON_SPECS: tuple[SeasonSpec, ...] = (
    SeasonSpec("25-26", 2025, "season_rating_2025_26"),
    SeasonSpec("24-25", 2024, "season_rating_2024_25"),
    SeasonSpec("23-24", 2023, "season_rating_2023_24"),
)
SEASON_SPECS_BY_LABEL = {spec.label: spec for spec in SEASON_SPECS}
SEASON_YEARS = tuple(spec.api_year for spec in SEASON_SPECS)
SEASON_FIELD_BY_YEAR = {spec.api_year: spec.field for spec in SEASON_SPECS}


@dataclass(frozen=True)
class SquadSyncReport:
    teams_processed: int
    players_written: int
    injuries_written: int
    warnings: tuple[str, ...]
    sources: tuple[str, ...]


@dataclass(frozen=True)
class SeasonSyncReport:
    season: str
    api_year: int
    teams_fetched: int
    players_updated: int
    requests_used: int
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class SeasonExtractionStatus:
    label: str
    api_year: int
    teams_cached: int
    teams_expected: int
    extracted_at: str | None
    complete: bool


def sync_squad_data(db: Session, *, refresh_ea_cache: bool = False, fetch_injuries_enabled: bool = True) -> SquadSyncReport:
    mappings = _load_transfermarkt_mappings()
    ea_players = load_ea_players(refresh=refresh_ea_cache)
    settings = get_settings()
    sources = ["transfermarkt.com (squads, market values)", "drop-api.ea.com (FC26 overall ratings)"]
    warnings: list[str] = []

    api_team_by_fifa = _load_api_team_mapping(settings, warnings)
    if api_team_by_fifa:
        sources = (*sources, "api-football.com (cached season performance ratings)")
    elif settings.api_football_key:
        warnings.append("API-Football team lookup failed — season ratings will use cache only")
    else:
        warnings.append("WC_API_FOOTBALL_KEY not set — run make squad-season-* after adding a key")

    season_by_team = _load_cached_season_data(api_team_by_fifa, mappings.keys())

    if fetch_injuries_enabled:
        sources = (*sources, "transfermarkt.com (injury history)")

    players_written = 0
    injuries_written = 0
    teams_processed = 0

    for fifa_code, tm_club_id in mappings.items():
        team = db.scalar(select(Team).where(Team.fifa_code == fifa_code))
        if team is None:
            warnings.append(f"No tournament team for FIFA code {fifa_code}")
            continue
        try:
            tm_squad = load_team_squad(tm_club_id)
            club = fetch_club(tm_club_id)
            abbr = club["baseDetails"]["abbreviation"]
            if not club["baseDetails"]["isNationalTeam"]:
                warnings.append(f"{fifa_code}: Transfermarkt ID {tm_club_id} is not a national team ({club['name']})")
                continue
            if abbr and abbr.upper() not in {fifa_code, "BIH", "CIV", "KOR"} and abbr.upper() != fifa_code[:3]:
                warnings.append(f"{fifa_code}: TM abbreviation {abbr} for {club['name']} — verify mapping")
        except Exception as exc:
            warnings.append(f"{fifa_code}: Transfermarkt squad fetch failed ({exc})")
            continue

        db.execute(delete(PlayerInjury).where(PlayerInjury.player_id.in_(
            select(SquadPlayer.id).where(SquadPlayer.team_id == team.id)
        )))
        db.execute(delete(SquadPlayer).where(SquadPlayer.team_id == team.id))
        db.flush()

        used_numbers: set[int] = set()
        next_fallback = 90
        for tm_player in sorted(tm_squad, key=lambda row: (-row.market_value_meur, row.squad_number, row.name)):
            squad_number = tm_player.squad_number
            if squad_number <= 0 or squad_number in used_numbers:
                while next_fallback in used_numbers:
                    next_fallback += 1
                squad_number = next_fallback
                next_fallback += 1
            used_numbers.add(squad_number)
            fc26 = match_ea_overall(tm_player.name, fifa_code, ea_players)
            if fc26 is None:
                warnings.append(f"{fifa_code}: no EA FC rating match for {tm_player.name}")
                fc26 = 60

            season_ratings = _season_ratings(tm_player.name, season_by_team.get(fifa_code, {}))
            player = SquadPlayer(
                team_id=team.id,
                name=tm_player.name,
                position=tm_player.position,
                squad_number=squad_number,
                fc26_overall=fc26,
                market_value_meur=tm_player.market_value_meur,
                season_rating_2025_26=season_ratings.get(2025),
                season_rating_2024_25=season_ratings.get(2024),
                season_rating_2023_24=season_ratings.get(2023),
            )
            db.add(player)
            db.flush()
            players_written += 1

            if fetch_injuries_enabled:
                try:
                    for injury in fetch_injuries(tm_player.tm_id):
                        db.add(PlayerInjury(
                            player_id=player.id,
                            started_on=injury.started_on,
                            ended_on=injury.ended_on,
                            days_out=injury.days_out,
                        ))
                        injuries_written += 1
                except Exception as exc:
                    warnings.append(f"{fifa_code}/{tm_player.name}: injury fetch failed ({exc})")

        teams_processed += 1

    db.commit()
    _write_seed_csvs(db)
    return SquadSyncReport(
        teams_processed=teams_processed,
        players_written=players_written,
        injuries_written=injuries_written,
        warnings=tuple(warnings[:100]),
        sources=tuple(sources),
    )


def sync_season_performance(db: Session, season_label: str) -> SeasonSyncReport:
    spec = SEASON_SPECS_BY_LABEL.get(season_label)
    if spec is None:
        valid = ", ".join(SEASON_SPECS_BY_LABEL)
        raise ValueError(f"Unknown season {season_label!r}; expected one of: {valid}")

    settings = get_settings()
    if not settings.api_football_key:
        raise RuntimeError("WC_API_FOOTBALL_KEY is required for season performance extraction")

    warnings: list[str] = []
    api_team_by_fifa = _load_api_team_mapping(settings, warnings)
    mappings = _load_transfermarkt_mappings()
    teams_fetched = 0
    players_updated = 0
    requests_used = 0

    squad_count = db.scalar(select(SquadPlayer.id).limit(1))
    if squad_count is None:
        warnings.append("No squad in database — run make squad-data first")

    for fifa_code in mappings:
        if fifa_code not in api_team_by_fifa:
            warnings.append(f"{fifa_code}: no API-Football team mapping")
            continue

        api_team_id = api_team_by_fifa[fifa_code]
        cache_path = season_cache_path(api_team_id, spec.api_year)
        had_cache = cache_path.exists()
        try:
            rows = fetch_team_players(api_team_id, spec.api_year)
        except Exception as exc:
            warnings.append(f"{fifa_code}: API-Football season {spec.label} failed ({exc})")
            continue

        if not had_cache:
            requests_used += 1
        teams_fetched += 1

        team = db.scalar(select(Team).where(Team.fifa_code == fifa_code))
        if team is None:
            continue
        players = db.scalars(select(SquadPlayer).where(SquadPlayer.team_id == team.id)).all()
        for player in players:
            rating = match_season_rating(player.name, rows) if rows else None
            setattr(player, spec.field, rating)
            if rating is not None:
                players_updated += 1

    _mark_season_extracted(spec, teams_fetched, len(mappings))
    db.commit()
    _write_seed_csvs(db)
    return SeasonSyncReport(
        season=spec.label,
        api_year=spec.api_year,
        teams_fetched=teams_fetched,
        players_updated=players_updated,
        requests_used=requests_used,
        warnings=tuple(warnings[:100]),
    )


def season_extraction_status() -> list[SeasonExtractionStatus]:
    mappings = _load_transfermarkt_mappings()
    expected = len(mappings)
    manifest = _load_extraction_manifest()
    api_team_by_fifa = _load_api_team_mapping(get_settings(), [])

    statuses: list[SeasonExtractionStatus] = []
    for spec in SEASON_SPECS:
        teams_cached = 0
        for fifa_code in mappings:
            api_team_id = api_team_by_fifa.get(fifa_code)
            if api_team_id is None:
                continue
            if season_cache_path(api_team_id, spec.api_year).exists():
                teams_cached += 1
        entry = manifest.get(spec.label, {})
        statuses.append(SeasonExtractionStatus(
            label=spec.label,
            api_year=spec.api_year,
            teams_cached=teams_cached,
            teams_expected=expected,
            extracted_at=entry.get("extracted_at"),
            complete=teams_cached >= expected and expected > 0,
        ))
    return statuses


def _load_api_team_mapping(settings, warnings: list[str]) -> dict[str, int]:
    if not settings.api_football_key:
        return {}
    try:
        return {
            team.fifa_code.upper(): team.api_id
            for team in fetch_world_cup_teams()
            if team.fifa_code
        }
    except Exception as exc:
        warnings.append(f"API-Football team lookup failed: {exc}")
        return {}


def _load_cached_season_data(api_team_by_fifa: dict[str, int], fifa_codes) -> dict[str, dict[int, list]]:
    season_by_team: dict[str, dict[int, list]] = {}
    for fifa_code in fifa_codes:
        api_team_id = api_team_by_fifa.get(fifa_code)
        if api_team_id is None:
            continue
        season_by_team[fifa_code] = {}
        for api_year in SEASON_YEARS:
            rows = load_team_players_cached(api_team_id, api_year)
            if rows is not None:
                season_by_team[fifa_code][api_year] = rows
    return season_by_team


def _season_ratings(name: str, season_rows: dict[int, list]) -> dict[int, float | None]:
    output: dict[int, float | None] = {}
    for api_year in SEASON_YEARS:
        rows = season_rows.get(api_year, [])
        output[api_year] = match_season_rating(name, rows) if rows else None
    return output


def _load_transfermarkt_mappings() -> dict[str, int]:
    path = SEED_DIR / "transfermarkt_teams.csv"
    mappings: dict[str, int] = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            mappings[row["fifa_code"].upper()] = int(row["tm_club_id"])
    return mappings


def _load_extraction_manifest() -> dict[str, dict[str, str]]:
    if not EXTRACTION_STATUS_PATH.exists():
        return {}
    return json.loads(EXTRACTION_STATUS_PATH.read_text(encoding="utf-8"))


def _mark_season_extracted(spec: SeasonSpec, teams_fetched: int, teams_expected: int) -> None:
    manifest = _load_extraction_manifest()
    manifest[spec.label] = {
        "api_year": str(spec.api_year),
        "extracted_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "teams_fetched": str(teams_fetched),
        "teams_expected": str(teams_expected),
    }
    EXTRACTION_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    EXTRACTION_STATUS_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _write_seed_csvs(db: Session) -> None:
    squad_path = SEED_DIR / "squad.csv"
    injury_path = SEED_DIR / "player_injuries.csv"
    squad_fields = [
        "fifa_code", "name", "position", "squad_number", "fc26_overall", "market_value_meur",
        "season_rating_2025_26", "season_rating_2024_25", "season_rating_2023_24",
    ]
    injury_fields = ["fifa_code", "player_name", "started_on", "ended_on", "days_out"]

    squad_rows: list[dict[str, str | int | float]] = []
    injury_rows: list[dict[str, str | int]] = []
    teams = {team.id: team for team in db.scalars(select(Team)).all()}
    players = db.scalars(select(SquadPlayer)).all()
    player_ids = [player.id for player in players]
    injuries = db.scalars(select(PlayerInjury).where(PlayerInjury.player_id.in_(player_ids))).all() if player_ids else []
    injury_by_player: dict[int, list[PlayerInjury]] = {}
    for injury in injuries:
        injury_by_player.setdefault(injury.player_id, []).append(injury)

    for player in players:
        team = teams[player.team_id]
        squad_rows.append({
            "fifa_code": team.fifa_code,
            "name": player.name,
            "position": player.position,
            "squad_number": player.squad_number,
            "fc26_overall": player.fc26_overall,
            "market_value_meur": player.market_value_meur,
            "season_rating_2025_26": player.season_rating_2025_26 or "",
            "season_rating_2024_25": player.season_rating_2024_25 or "",
            "season_rating_2023_24": player.season_rating_2023_24 or "",
        })
        for injury in injury_by_player.get(player.id, []):
            injury_rows.append({
                "fifa_code": team.fifa_code,
                "player_name": player.name,
                "started_on": injury.started_on.isoformat(),
                "ended_on": injury.ended_on.isoformat() if injury.ended_on else "",
                "days_out": injury.days_out,
            })

    with squad_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=squad_fields)
        writer.writeheader()
        writer.writerows(squad_rows)
    with injury_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=injury_fields)
        writer.writeheader()
        writer.writerows(injury_rows)
