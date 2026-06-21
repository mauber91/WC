from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from world_cup_api.db.models import Match, MatchResult


def revise_result(db: Session, match_id: int, payload: dict) -> MatchResult:
    match = db.get(Match, match_id)
    if match is None:
        raise LookupError("Match not found")
    now = datetime.now(timezone.utc)
    current = db.scalar(select(MatchResult).where(MatchResult.match_id == match_id, MatchResult.is_current.is_(True)))
    if current:
        current.is_current = False
        current.superseded_at = now
    revision = int(db.scalar(select(func.max(MatchResult.revision)).where(MatchResult.match_id == match_id)) or 0) + 1
    result = MatchResult(match_id=match_id, revision=revision, is_current=True, recorded_at=now,
                         source_updated_at=payload.pop("source_updated_at", now), **payload)
    db.add(result)
    match.status = "final"
    db.commit()
    db.refresh(result)
    return result


def remove_current_result(db: Session, match_id: int) -> None:
    current = db.scalar(select(MatchResult).where(MatchResult.match_id == match_id, MatchResult.is_current.is_(True)))
    if current is None:
        raise LookupError("Current result not found")
    current.is_current = False
    current.superseded_at = datetime.now(timezone.utc)
    match = db.get(Match, match_id)
    if match:
        match.status = "scheduled"
    db.commit()
