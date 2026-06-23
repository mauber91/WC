from datetime import datetime, timezone

from world_cup_api.services.seed import seed_database
from world_cup_api.services.simulation_coverage import (
    compute_result_coverage,
    locked_match_numbers_from_snapshot,
)
from world_cup_api.simulation.engine import build_input_snapshot


def test_locked_match_numbers_from_snapshot_uses_explicit_list(db_session) -> None:
    seed_database(db_session)
    snapshot, _ = build_input_snapshot(db_session)
    locked = locked_match_numbers_from_snapshot(snapshot)
    assert locked
    assert snapshot["locked_match_numbers"] == sorted(locked)


def test_compute_result_coverage_marks_stale_when_results_added_after_snapshot(db_session) -> None:
    from sqlalchemy import select

    from world_cup_api.db.models import Match, Simulation
    from world_cup_api.services.results import revise_result

    seed_database(db_session)
    snapshot, input_hash = build_input_snapshot(db_session)
    run = Simulation(
        id="coverage-test",
        tournament_id=snapshot["tournament_id"],
        status="completed",
        iterations=10_000,
        progress_iterations=10_000,
        seed=2026,
        input_cutoff_at=datetime.now(timezone.utc),
        input_hash=input_hash,
        input_snapshot_json=snapshot,
        ruleset_version="test",
        model_version="test",
        engine_version="engine-v3",
    )
    db_session.add(run)
    db_session.commit()

    fresh = compute_result_coverage(db_session, run)
    assert fresh.is_stale is False
    assert fresh.last_locked_match_number == max(snapshot["locked_match_numbers"])
    assert fresh.last_locked_match_label is not None
    assert " vs " in fresh.last_locked_match_label

    unfinished = db_session.scalar(
        select(Match)
        .where(Match.status != "final", Match.team_a_id.is_not(None), Match.team_b_id.is_not(None))
        .order_by(Match.official_match_number)
    )
    assert unfinished is not None
    revise_result(
        db_session,
        unfinished.id,
        {
            "team_a_goals_90": 2,
            "team_b_goals_90": 1,
            "team_a_yellows": 0,
            "team_b_yellows": 0,
            "team_a_indirect_reds": 0,
            "team_b_indirect_reds": 0,
            "team_a_direct_reds": 0,
            "team_b_direct_reds": 0,
            "team_a_yellow_direct_reds": 0,
            "team_b_yellow_direct_reds": 0,
        },
    )

    stale = compute_result_coverage(db_session, run)
    assert stale.is_stale is True
    assert stale.stale_before_match_number == unfinished.official_match_number
    assert stale.pending_result_count == 1
    assert stale.stale_before_match_label is not None
