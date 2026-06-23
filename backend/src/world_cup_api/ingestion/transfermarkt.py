from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from world_cup_api.ingestion.fetch_json import RAW_DIR, fetch_json, load_cache, save_cache

TM_BASE = "https://tmapi-alpha.transfermarkt.technology"
POSITION_MAP = {
    "GOALKEEPER": "GK",
    "DEFENDER": "CB",
    "MIDFIELD": "CM",
    "FORWARD": "ST",
}


@dataclass(frozen=True)
class TmPlayer:
    tm_id: str
    name: str
    position: str
    squad_number: int
    market_value_meur: float


@dataclass(frozen=True)
class TmInjury:
    started_on: date
    ended_on: date | None
    days_out: int
    name: str


def _position_short(attributes: dict[str, Any]) -> str:
    position = attributes.get("position") or {}
    short = position.get("shortName")
    if short:
        return str(short).upper()
    group = str(attributes.get("positionGroup") or "").upper()
    return POSITION_MAP.get(group, "CM")


def fetch_club(club_id: int) -> dict[str, Any]:
    payload = fetch_json(f"{TM_BASE}/club/{club_id}", pause_seconds=1.2)
    return payload["data"]


def fetch_squad(club_id: int) -> list[dict[str, Any]]:
    payload = fetch_json(f"{TM_BASE}/club/{club_id}/squad", pause_seconds=1.2)
    return payload["data"]["squad"]


def fetch_players(player_ids: list[str]) -> list[dict[str, Any]]:
    if not player_ids:
        return []
    chunks: list[dict[str, Any]] = []
    batch_size = 20
    for start in range(0, len(player_ids), batch_size):
        batch = player_ids[start:start + batch_size]
        query = "&".join(f"ids[]={player_id}" for player_id in batch)
        payload = fetch_json(f"{TM_BASE}/players?{query}", pause_seconds=1.2)
        chunks.extend(payload["data"])
    return chunks


def fetch_injuries(player_id: str) -> list[TmInjury]:
    payload = fetch_json(f"{TM_BASE}/player/{player_id}/injury", pause_seconds=0.8)
    injuries: list[TmInjury] = []
    for row in payload.get("data", {}).get("injuries", []):
        started = date.fromisoformat(row["start"])
        ended = date.fromisoformat(row["end"]) if row.get("end") else None
        days = int(row.get("durationDetails", {}).get("days") or 0)
        injuries.append(TmInjury(started_on=started, ended_on=ended, days_out=days, name=row.get("name") or "Injury"))
    return injuries


def load_team_squad(club_id: int, *, cache: bool = True) -> list[TmPlayer]:
    cache_path = RAW_DIR / "transfermarkt" / f"club_{club_id}_squad.json"
    if cache:
        cached = load_cache(cache_path)
        if cached is not None:
            return [_player_from_cache(row) for row in cached]

    squad_rows = fetch_squad(club_id)
    player_ids = [str(row["playerId"]) for row in squad_rows]
    profiles = fetch_players(player_ids)
    profile_by_id = {str(row["id"]): row for row in profiles}
    number_by_id = {
        str(row["playerId"]): int(row["shirtNumber"])
        for row in squad_rows
        if row.get("shirtNumber") is not None
    }

    players: list[TmPlayer] = []
    serializable: list[dict[str, Any]] = []
    for player_id, profile in profile_by_id.items():
        market = profile.get("marketValueDetails", {}).get("current", {}).get("value")
        player = TmPlayer(
            tm_id=player_id,
            name=profile["name"],
            position=_position_short(profile.get("attributes", {})),
            squad_number=number_by_id.get(player_id, 0),
            market_value_meur=round(float(market or 0) / 1_000_000, 2),
        )
        players.append(player)
        serializable.append({
            "tm_id": player.tm_id,
            "name": player.name,
            "position": player.position,
            "squad_number": player.squad_number,
            "market_value_meur": player.market_value_meur,
        })
    if cache:
        save_cache(cache_path, serializable)
    return players


def _player_from_cache(row: dict[str, Any]) -> TmPlayer:
    return TmPlayer(
        tm_id=str(row["tm_id"]),
        name=str(row["name"]),
        position=str(row["position"]),
        squad_number=int(row["squad_number"]),
        market_value_meur=float(row["market_value_meur"]),
    )
