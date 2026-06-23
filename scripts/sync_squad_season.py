#!/usr/bin/env python3
"""Fetch API-Football season performance for one football season at a time."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from world_cup_api.db import Base, SessionLocal, engine
from world_cup_api.services.seed import seed_database
from world_cup_api.services.squad_sync import SEASON_SPECS_BY_LABEL, season_extraction_status, sync_season_performance


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync one season of API-Football performance data")
    parser.add_argument(
        "--season",
        choices=sorted(SEASON_SPECS_BY_LABEL),
        help="Football season label (e.g. 24-25)",
    )
    parser.add_argument("--status", action="store_true", help="Show extraction progress for all seasons")
    args = parser.parse_args()

    if args.status:
        statuses = season_extraction_status()
        print(json.dumps([
            {
                "season": status.label,
                "api_year": status.api_year,
                "teams_cached": status.teams_cached,
                "teams_expected": status.teams_expected,
                "complete": status.complete,
                "extracted_at": status.extracted_at,
            }
            for status in statuses
        ], indent=2))
        return

    if not args.season:
        parser.error("Provide --season or --status")

    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_database(db)
        report = sync_season_performance(db, args.season)
    print(json.dumps({
        "season": report.season,
        "api_year": report.api_year,
        "teams_fetched": report.teams_fetched,
        "players_updated": report.players_updated,
        "requests_used": report.requests_used,
        "warnings": list(report.warnings),
    }, indent=2))


if __name__ == "__main__":
    main()
