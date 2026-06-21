#!/usr/bin/env python3
"""Refresh finished group-stage results from FIFA and regenerate seed CSVs."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from world_cup_api.db import Base, SessionLocal, engine
from world_cup_api.services.seed import seed_database
from world_cup_api.services.tournament_refresh import refresh_tournament_data


def main() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_database(db)
        report = refresh_tournament_data(db, regenerate_seed_files=True)
    print(json.dumps({
        "fetched": report.fetched,
        "applied": report.applied,
        "skipped": report.skipped,
        "seed_regenerated": report.seed_regenerated,
        "warnings": list(report.warnings),
    }, indent=2))


if __name__ == "__main__":
    main()
