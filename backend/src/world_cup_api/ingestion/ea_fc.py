from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from world_cup_api.domain.name_match import normalize_name, names_match
from world_cup_api.ingestion.fetch_json import RAW_DIR, fetch_json, load_cache, save_cache

EA_BASE = "https://drop-api.ea.com/rating/ea-sports-fc"
EA_PAGE_SIZE = 100

NATIONALITY_TO_FIFA: dict[str, str] = {
    "england": "ENG",
    "france": "FRA",
    "germany": "GER",
    "spain": "ESP",
    "portugal": "POR",
    "netherlands": "NED",
    "belgium": "BEL",
    "croatia": "CRO",
    "italy": "ITA",
    "brazil": "BRA",
    "argentina": "ARG",
    "uruguay": "URU",
    "colombia": "COL",
    "ecuador": "ECU",
    "paraguay": "PAR",
    "mexico": "MEX",
    "united states": "USA",
    "canada": "CAN",
    "japan": "JPN",
    "korea republic": "KOR",
    "australia": "AUS",
    "saudi arabia": "KSA",
    "iran": "IRN",
    "qatar": "QAT",
    "morocco": "MAR",
    "senegal": "SEN",
    "ghana": "GHA",
    "cameroon": "CMR",
    "nigeria": "NGA",
    "algeria": "ALG",
    "tunisia": "TUN",
    "egypt": "EGY",
    "south africa": "RSA",
    "côte d'ivoire": "CIV",
    "cote d'ivoire": "CIV",
    "ivory coast": "CIV",
    "dr congo": "COD",
    "congo dr": "COD",
    "cabo verde": "CPV",
    "cape verde": "CPV",
    "switzerland": "SUI",
    "austria": "AUT",
    "scotland": "SCO",
    "norway": "NOR",
    "sweden": "SWE",
    "türkiye": "TUR",
    "turkey": "TUR",
    "czechia": "CZE",
    "czech republic": "CZE",
    "bosnia-herzegovina": "BIH",
    "bosnia and herzegovina": "BIH",
    "haiti": "HAI",
    "panama": "PAN",
    "new zealand": "NZL",
    "uzbekistan": "UZB",
    "iraq": "IRQ",
    "jordan": "JOR",
    "curaçao": "CUW",
    "curacao": "CUW",
}


@dataclass(frozen=True)
class EaPlayer:
    ea_id: int
    name: str
    nationality: str
    fifa_code: str | None
    position: str
    overall: int


def _display_name(row: dict[str, Any]) -> str:
    if row.get("commonName"):
        return str(row["commonName"])
    return f"{row.get('firstName', '').strip()} {row.get('lastName', '').strip()}".strip()


def _fifa_code(row: dict[str, Any]) -> str | None:
    nationality = normalize_name(str((row.get("nationality") or {}).get("label") or ""))
    return NATIONALITY_TO_FIFA.get(nationality)


def load_ea_players(*, cache: bool = True, refresh: bool = False) -> list[EaPlayer]:
    cache_path = RAW_DIR / "ea_fc" / "players.json"
    if cache and not refresh:
        cached = load_cache(cache_path)
        if cached is not None:
            return [_player_from_cache(row) for row in cached]

    rows: list[dict[str, Any]] = []
    offset = 0
    total = None
    while total is None or offset < total:
        payload = fetch_json(f"{EA_BASE}?limit={EA_PAGE_SIZE}&offset={offset}", pause_seconds=0.4)
        total = int(payload["totalItems"])
        rows.extend(payload["items"])
        offset += EA_PAGE_SIZE

    players = [_player_from_row(row) for row in rows]
    if cache:
        save_cache(cache_path, [
            {
                "ea_id": player.ea_id,
                "name": player.name,
                "nationality": player.nationality,
                "fifa_code": player.fifa_code,
                "position": player.position,
                "overall": player.overall,
            }
            for player in players
        ])
    return players


def match_ea_overall(name: str, fifa_code: str, players: list[EaPlayer]) -> int | None:
    candidates = [player for player in players if player.fifa_code == fifa_code and names_match(name, player.name)]
    if not candidates:
        candidates = [player for player in players if names_match(name, player.name)]
    if not candidates:
        return None
    return max(player.overall for player in candidates)


def _player_from_row(row: dict[str, Any]) -> EaPlayer:
    position = str((row.get("position") or {}).get("shortLabel") or "CM")
    nationality = str((row.get("nationality") or {}).get("label") or "")
    return EaPlayer(
        ea_id=int(row["id"]),
        name=_display_name(row),
        nationality=nationality,
        fifa_code=_fifa_code(row),
        position=position,
        overall=int(row["overallRating"]),
    )


def _player_from_cache(row: dict[str, Any]) -> EaPlayer:
    return EaPlayer(
        ea_id=int(row["ea_id"]),
        name=str(row["name"]),
        nationality=str(row["nationality"]),
        fifa_code=row.get("fifa_code"),
        position=str(row["position"]),
        overall=int(row["overall"]),
    )
