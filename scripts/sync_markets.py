#!/usr/bin/env python3
"""Sync Polymarket and Kalshi quotes for upcoming fixtures via Attena search."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from world_cup_api.db import Base, SessionLocal, engine
from world_cup_api.services.market_sync import sync_upcoming_markets
from world_cup_api.services.seed import seed_database


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync prediction markets from Attena")
    parser.add_argument("--match-number", type=int, action="append", dest="match_numbers")
    args = parser.parse_args()

    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_database(db)
        reports = sync_upcoming_markets(db, match_numbers=args.match_numbers)
    print(json.dumps([
        {
            "match_number": report.match_number,
            "attena_hits": report.attena_hits,
            "stored_rows": report.stored_rows,
            "platforms": list(report.platforms),
            "warnings": list(report.warnings),
        }
        for report in reports
    ], indent=2))


if __name__ == "__main__":
    main()
