from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from world_cup_api.db.models import (
    Simulation, SimulationBracketResult, SimulationGroupResult, SimulationTeamR32Rival, SimulationTeamResult, Tournament,
)
from world_cup_api.db.session import SessionLocal
from world_cup_api.config import get_settings
from world_cup_api.simulation.engine import build_input_snapshot, run_trials_parallel


def backfill_r32_rivals(db: Session, simulation_id: str) -> int:
    run = db.get(Simulation, simulation_id)
    if run is None:
        raise LookupError(f"Simulation {simulation_id} not found")
    if run.status != "completed":
        raise ValueError(f"Simulation {simulation_id} is not completed")

    output = run_trials_parallel(
        run.input_snapshot_json,
        run.iterations,
        run.seed,
        get_settings().simulation_max_workers,
    )
    db.execute(delete(SimulationTeamR32Rival).where(SimulationTeamR32Rival.simulation_id == simulation_id))
    rows_written = 0
    for (team_id, finish_position, opponent_id), count in output["r32_rivals"].items():
        db.add(SimulationTeamR32Rival(
            simulation_id=simulation_id,
            team_id=team_id,
            finish_position=finish_position,
            opponent_team_id=opponent_id,
            meeting_count=count,
        ))
        rows_written += 1
    db.commit()
    return rows_written


def create_simulation(db: Session, iterations: int, seed: int, force: bool = False) -> Simulation:
    snapshot, input_hash = build_input_snapshot(db)
    tournament = db.scalar(select(Tournament).where(Tournament.code == "FWC2026"))
    assert tournament is not None
    existing = db.scalar(select(Simulation).where(
        Simulation.input_hash == input_hash, Simulation.iterations == iterations, Simulation.seed == seed,
        Simulation.status == "completed", Simulation.engine_version == "engine-v3",
    ))
    if existing and not force:
        return existing
    run = Simulation(id=str(uuid.uuid4()), tournament_id=tournament.id, status="queued", iterations=iterations,
                     progress_iterations=0, seed=seed, input_cutoff_at=datetime.fromisoformat(snapshot["cutoff"]),
                     input_hash=input_hash, input_snapshot_json=snapshot, ruleset_version=tournament.ruleset_version,
                     model_version="nbinom-fused-strength-v1", engine_version="engine-v3")
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def execute_simulation(simulation_id: str) -> None:
    db = SessionLocal()
    start = time.perf_counter()
    try:
        run = db.get(Simulation, simulation_id)
        if run is None:
            return
        run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        db.commit()

        def progress(value: int) -> None:
            current = db.get(Simulation, simulation_id)
            if current:
                current.progress_iterations = value
                db.commit()

        def cancelled() -> bool:
            db.expire_all()
            current = db.get(Simulation, simulation_id)
            return bool(current and current.cancel_requested)

        output = run_trials_parallel(run.input_snapshot_json, run.iterations, run.seed,
                                     get_settings().simulation_max_workers, progress, cancelled)
        run = db.get(Simulation, simulation_id)
        assert run is not None
        db.execute(delete(SimulationTeamResult).where(SimulationTeamResult.simulation_id == simulation_id))
        db.execute(delete(SimulationGroupResult).where(SimulationGroupResult.simulation_id == simulation_id))
        db.execute(delete(SimulationBracketResult).where(SimulationBracketResult.simulation_id == simulation_id))
        db.execute(delete(SimulationTeamR32Rival).where(SimulationTeamR32Rival.simulation_id == simulation_id))
        for team_id, counts in output["teams"].items():
            db.add(SimulationTeamResult(
                simulation_id=simulation_id, team_id=team_id,
                finish_1_count=counts["finish_1"], finish_2_count=counts["finish_2"],
                finish_3_count=counts["finish_3"], finish_4_count=counts["finish_4"],
                advance_as_third_count=counts["advance_as_third"], round_of_32_count=counts["round_of_32"],
                round_of_16_count=counts["round_of_16"], quarterfinal_count=counts["quarterfinal"],
                semifinal_count=counts["semifinal"], final_count=counts["final"], champion_count=counts["champion"],
                sum_group_points=counts["sum_points"], sum_group_goals_for=counts["sum_gf"],
                sum_group_goals_against=counts["sum_ga"],
            ))
        for key, count in output["groups"].items():
            group_id, *teams = key
            db.add(SimulationGroupResult(simulation_id=simulation_id, group_id=group_id,
                                         rank_1_team_id=teams[0], rank_2_team_id=teams[1],
                                         rank_3_team_id=teams[2], rank_4_team_id=teams[3], occurrence_count=count))
        for (number, team_a, team_b), counts in output["bracket"].items():
            db.add(SimulationBracketResult(simulation_id=simulation_id, official_match_number=number,
                                           team_a_id=team_a, team_b_id=team_b,
                                           meeting_count=counts["meetings"], team_a_advance_count=counts["a_wins"]))
        for (team_id, finish_position, opponent_id), count in output["r32_rivals"].items():
            db.add(SimulationTeamR32Rival(
                simulation_id=simulation_id,
                team_id=team_id,
                finish_position=finish_position,
                opponent_team_id=opponent_id,
                meeting_count=count,
            ))
        run.progress_iterations = output["completed"]
        run.status = "cancelled" if run.cancel_requested else "completed"
        run.completed_at = datetime.now(timezone.utc)
        run.duration_ms = int((time.perf_counter() - start) * 1000)
        db.commit()
    except Exception as exc:
        db.rollback()
        run = db.get(Simulation, simulation_id)
        if run:
            run.status = "failed"
            run.error_message = str(exc)
            run.completed_at = datetime.now(timezone.utc)
            db.commit()
        raise
    finally:
        db.close()
