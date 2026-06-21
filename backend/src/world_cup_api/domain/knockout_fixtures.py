from __future__ import annotations

import csv
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from world_cup_api.config import ROOT_DIR

SEED_DIR = ROOT_DIR / "data" / "seed"


@lru_cache
def _rows() -> list[dict[str, str]]:
    path = SEED_DIR / "knockout_fixtures.csv"
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


@lru_cache
def knockout_venues() -> dict[int, str]:
    return {int(row["match_number"]): row["host_country"].upper() for row in _rows()}


@lru_cache
def knockout_schedule() -> dict[int, datetime]:
    return {
        int(row["match_number"]): datetime.fromisoformat(row["scheduled_at"].replace("Z", "+00:00"))
        for row in _rows()
    }


@lru_cache
def knockout_venue_names() -> dict[int, str]:
    return {int(row["match_number"]): row["venue"] for row in _rows()}
