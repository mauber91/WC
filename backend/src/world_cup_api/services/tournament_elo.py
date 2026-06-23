from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from world_cup_api.db.models import Match, MatchResult, TeamRating, TournamentTeam
from world_cup_api.domain.tournament_elo import build_elo_table


def baseline_elos(db: Session, tournament_id: int) -> dict[int, float]:
    team_ids = db.scalars(
        select(TournamentTeam.team_id).where(TournamentTeam.tournament_id == tournament_id)
    ).all()
    baseline: dict[int, float] = {}
    for team_id in team_ids:
        value = db.scalar(
            select(TeamRating.rating_value)
            .where(
                TeamRating.team_id == team_id,
                TeamRating.rating_type == "ELO",
                TeamRating.effective_at <= datetime.now(timezone.utc),
            )
            .order_by(TeamRating.effective_at.desc())
            .limit(1)
        )
        baseline[team_id] = float(value if value is not None else 1500)
    return baseline


def completed_tournament_results(db: Session, tournament_id: int) -> list[tuple[int, int, int, int]]:
    rows = db.execute(
        select(Match.team_a_id, Match.team_b_id, MatchResult.team_a_goals_90, MatchResult.team_b_goals_90)
        .join(MatchResult, MatchResult.match_id == Match.id)
        .where(
            Match.tournament_id == tournament_id,
            MatchResult.is_current.is_(True),
            Match.team_a_id.is_not(None),
            Match.team_b_id.is_not(None),
        )
        .order_by(Match.scheduled_at, Match.official_match_number)
    ).all()
    return [(row[0], row[1], row[2], row[3]) for row in rows]


def current_tournament_elos(db: Session, tournament_id: int) -> dict[int, float]:
    return build_elo_table(baseline_elos(db, tournament_id), completed_tournament_results(db, tournament_id))


def team_elo(db: Session, tournament_id: int, team_id: int) -> float:
    return current_tournament_elos(db, tournament_id)[team_id]
