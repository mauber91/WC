from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from world_cup_api.config import get_settings
from world_cup_api.domain.name_match import names_match
from world_cup_api.ingestion.fetch_json import RAW_DIR, fetch_json, load_cache, save_cache

API_BASE = "https://v3.football.api-sports.io"
WORLD_CUP_LEAGUE_ID = 1
WORLD_CUP_SEASON = 2026
POSITION_MAP = {"Goalkeeper": "GK", "Defender": "CB", "Midfielder": "CM", "Attacker": "ST"}


@dataclass(frozen=True)
class ApiFootballTeam:
    api_id: int
    name: str
    fifa_code: str | None


@dataclass(frozen=True)
class ApiFootballPlayerSeason:
    player_id: int
    name: str
    season: int
    rating: float | None


def _headers() -> dict[str, str]:
    settings = get_settings()
    if not settings.api_football_key:
        raise RuntimeError("WC_API_FOOTBALL_KEY is required for season performance ratings")
    return {"x-apisports-key": settings.api_football_key}


def fetch_world_cup_teams(*, cache: bool = True) -> list[ApiFootballTeam]:
    cache_path = RAW_DIR / "api_football" / "world_cup_teams.json"
    if cache:
        cached = load_cache(cache_path)
        if cached is not None:
            return [_team_from_cache(row) for row in cached]
    payload = fetch_json(
        f"{API_BASE}/teams?league={WORLD_CUP_LEAGUE_ID}&season={WORLD_CUP_SEASON}",
        headers=_headers(),
        pause_seconds=1.0,
    )
    teams = [
        ApiFootballTeam(
            api_id=int(row["team"]["id"]),
            name=str(row["team"]["name"]),
            fifa_code=row["team"].get("code") or None,
        )
        for row in payload.get("response", [])
    ]
    if cache:
        save_cache(cache_path, [{"api_id": t.api_id, "name": t.name, "fifa_code": t.fifa_code} for t in teams])
    return teams


def season_cache_path(team_id: int, season: int) -> Path:
    return RAW_DIR / "api_football" / f"team_{team_id}_season_{season}.json"


def load_team_players_cached(team_id: int, season: int) -> list[ApiFootballPlayerSeason] | None:
    cached = load_cache(season_cache_path(team_id, season))
    if cached is None:
        return None
    return [_season_from_cache(row) for row in cached]


def fetch_team_players(team_id: int, season: int, *, cache: bool = True) -> list[ApiFootballPlayerSeason]:
    cache_path = season_cache_path(team_id, season)
    if cache:
        cached = load_cache(cache_path)
        if cached is not None:
            return [_season_from_cache(row) for row in cached]

    page = 1
    total_pages = 1
    rows: list[ApiFootballPlayerSeason] = []
    serializable: list[dict[str, Any]] = []
    while page <= total_pages:
        payload = fetch_json(
            f"{API_BASE}/players?team={team_id}&season={season}&page={page}",
            headers=_headers(),
            pause_seconds=1.0,
        )
        total_pages = int(payload.get("paging", {}).get("total", 1))
        for item in payload.get("response", []):
            player = item.get("player") or {}
            stats = item.get("statistics") or []
            rating = _aggregate_rating(stats)
            row = ApiFootballPlayerSeason(
                player_id=int(player["id"]),
                name=str(player.get("name") or ""),
                season=season,
                rating=rating,
            )
            rows.append(row)
            serializable.append({
                "player_id": row.player_id,
                "name": row.name,
                "season": row.season,
                "rating": row.rating,
            })
        page += 1
    if cache:
        save_cache(cache_path, serializable)
    return rows


def match_season_rating(name: str, season_rows: list[ApiFootballPlayerSeason]) -> float | None:
    matches = [row for row in season_rows if names_match(name, row.name)]
    if not matches:
        return None
    ratings = [row.rating for row in matches if row.rating is not None]
    if not ratings:
        return None
    return max(ratings)


def _aggregate_rating(stats: list[dict[str, Any]]) -> float | None:
    ratings: list[float] = []
    for block in stats:
        games = block.get("games") or {}
        rating = games.get("rating")
        if rating in (None, "0", 0, "0.0"):
            continue
        try:
            ratings.append(float(rating))
        except (TypeError, ValueError):
            continue
    if not ratings:
        return None
    return round(sum(ratings) / len(ratings), 1)


def _team_from_cache(row: dict[str, Any]) -> ApiFootballTeam:
    return ApiFootballTeam(api_id=int(row["api_id"]), name=str(row["name"]), fifa_code=row.get("fifa_code"))


def _season_from_cache(row: dict[str, Any]) -> ApiFootballPlayerSeason:
    return ApiFootballPlayerSeason(
        player_id=int(row["player_id"]),
        name=str(row["name"]),
        season=int(row["season"]),
        rating=float(row["rating"]) if row.get("rating") is not None else None,
    )
