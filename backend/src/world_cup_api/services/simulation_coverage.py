from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from world_cup_api.db.models import Match, MatchResult, Simulation, Team, Tournament


@dataclass(frozen=True)
class SimulationResultCoverage:
    is_stale: bool
    last_locked_match_number: int | None
    stale_before_match_number: int | None
    pending_result_count: int
    stale_before_match_label: str | None
    last_locked_match_label: str | None

    def to_dict(self) -> dict:
        return {
            "is_stale": self.is_stale,
            "last_locked_match_number": self.last_locked_match_number,
            "stale_before_match_number": self.stale_before_match_number,
            "pending_result_count": self.pending_result_count,
            "stale_before_match_label": self.stale_before_match_label,
            "last_locked_match_label": self.last_locked_match_label,
        }


def locked_match_numbers_from_snapshot(snapshot: dict) -> set[int]:
    if numbers := snapshot.get("locked_match_numbers"):
        return {int(value) for value in numbers}
    locked: set[int] = set()
    for group in snapshot.get("groups", {}).values():
        for item in group.get("matches", []):
            if "completed" not in item:
                continue
            number = item.get("official_match_number")
            if number is not None:
                locked.add(int(number))
    return locked


def current_result_match_numbers(db: Session, tournament_id: int) -> set[int]:
    rows = db.scalars(
        select(Match.official_match_number)
        .join(MatchResult, MatchResult.match_id == Match.id)
        .where(
            Match.tournament_id == tournament_id,
            MatchResult.is_current.is_(True),
        )
    ).all()
    return {int(value) for value in rows}


def compute_result_coverage(db: Session, run: Simulation) -> SimulationResultCoverage:
    snapshot = run.input_snapshot_json or {}
    tournament_id = int(snapshot.get("tournament_id") or run.tournament_id)
    locked = locked_match_numbers_from_snapshot(snapshot)
    current = current_result_match_numbers(db, tournament_id)
    pending = sorted(current - locked)
    last_locked = max(locked) if locked else None
    stale_before = pending[0] if pending else None
    return SimulationResultCoverage(
        is_stale=bool(pending),
        last_locked_match_number=last_locked,
        stale_before_match_number=stale_before,
        pending_result_count=len(pending),
        stale_before_match_label=_match_label(db, stale_before),
        last_locked_match_label=_match_label(db, last_locked),
    )


def _match_label(db: Session, official_match_number: int | None) -> str | None:
    if official_match_number is None:
        return None
    tournament = db.scalar(select(Tournament).where(Tournament.code == "FWC2026"))
    if tournament is None:
        return f"M{official_match_number}"
    team_a = aliased(Team)
    team_b = aliased(Team)
    row = db.execute(
        select(Match, team_a, team_b)
        .join(team_a, Match.team_a_id == team_a.id)
        .join(team_b, Match.team_b_id == team_b.id)
        .where(
            Match.tournament_id == tournament.id,
            Match.official_match_number == official_match_number,
        )
    ).first()
    if row is None:
        return f"M{official_match_number}"
    match, home, away = row
    return f"M{match.official_match_number} · {home.name} vs {away.name}"
