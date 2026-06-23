#!/usr/bin/env python3
from __future__ import annotations

import argparse

from sqlalchemy import select

from world_cup_api.db.models import Simulation
from world_cup_api.db.session import SessionLocal
from world_cup_api.services.simulations import backfill_r32_rivals


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill Round-of-32 rival counts for a completed simulation.")
    parser.add_argument("simulation_id", nargs="?", help="Simulation UUID (defaults to latest completed run)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        simulation_id = args.simulation_id
        if not simulation_id:
            run = db.scalar(
                select(Simulation)
                .where(Simulation.status == "completed")
                .order_by(Simulation.completed_at.desc(), Simulation.created_at.desc())
                .limit(1),
            )
            if run is None:
                raise SystemExit("No completed simulation found")
            simulation_id = run.id
            print(f"Using latest completed simulation {simulation_id} ({run.iterations:,} trials, seed {run.seed})")

        rows = backfill_r32_rivals(db, simulation_id)
        print(f"Wrote {rows:,} rival rows for simulation {simulation_id}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
