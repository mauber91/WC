#!/usr/bin/env python3
"""Sync real squad data from Transfermarkt, EA FC, and optional API-Football."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from world_cup_api.db import Base, SessionLocal, engine
from world_cup_api.services.seed import seed_database
from world_cup_api.services.squad_sync import sync_squad_data


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync squad data from external sources")
    parser.add_argument("--refresh-ea-cache", action="store_true", help="Re-download the EA FC player database")
    parser.add_argument("--skip-injuries", action="store_true", help="Skip per-player injury lookups")
    args = parser.parse_args()

    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_database(db)
        report = sync_squad_data(
            db,
            refresh_ea_cache=args.refresh_ea_cache,
            fetch_injuries_enabled=not args.skip_injuries,
        )
    print(json.dumps({
        "teams_processed": report.teams_processed,
        "players_written": report.players_written,
        "injuries_written": report.injuries_written,
        "sources": list(report.sources),
        "warnings": list(report.warnings),
    }, indent=2))


if __name__ == "__main__":
    main()
