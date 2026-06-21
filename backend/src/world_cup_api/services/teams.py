from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from world_cup_api.db.models import Group, Team, TeamRating, TournamentTeam
from world_cup_api.domain.teams import team_ref_matches, team_slug
from world_cup_api.services.squad import team_squad
from world_cup_api.services.tournament import group_standings, list_matches
from world_cup_api.services.tournament_elo import team_elo


def resolve_team(db: Session, ref: str) -> Team:
    if ref.isdigit():
        team = db.get(Team, int(ref))
        if team is not None:
            return team
    teams = db.scalars(select(Team)).all()
    matches = [team for team in teams if team_ref_matches(team.name, team.fifa_code, ref)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise LookupError("Ambiguous team reference")
    raise LookupError("Team not found")


def _latest_rating(db: Session, team_id: int, kind: str) -> float | None:
    value = db.scalar(
        select(TeamRating.rating_value)
        .where(
            TeamRating.team_id == team_id,
            TeamRating.rating_type == kind,
            TeamRating.effective_at <= datetime.now(timezone.utc),
        )
        .order_by(TeamRating.effective_at.desc())
        .limit(1)
    )
    return float(value) if value is not None else None


def _latest_fifa_rank(db: Session, team_id: int) -> int | None:
    rating = db.scalar(
        select(TeamRating)
        .where(
            TeamRating.team_id == team_id,
            TeamRating.rating_type == "FIFA_RANK",
            TeamRating.effective_at <= datetime.now(timezone.utc),
        )
        .order_by(TeamRating.effective_at.desc())
        .limit(1)
    )
    if rating is None:
        return None
    if rating.rank is not None:
        return int(rating.rank)
    return int(rating.rating_value)


def team_detail(db: Session, ref: str) -> dict:
    team = resolve_team(db, ref)
    membership = db.scalar(select(TournamentTeam).where(TournamentTeam.team_id == team.id))
    group_code: str | None = None
    is_host = False
    standing: dict | None = None
    if membership is not None:
        group = db.get(Group, membership.group_id)
        if group is not None:
            group_code = group.code
            is_host = membership.is_host
            _, table = group_standings(db, group.code)
            row = next((item for item in table.rows if item.team_id == team.id), None)
            if row is not None:
                standing = {
                    "position": row.position,
                    "played": row.played,
                    "won": row.won,
                    "drawn": row.drawn,
                    "lost": row.lost,
                    "goals_for": row.goals_for,
                    "goals_against": row.goals_against,
                    "goal_difference": row.goal_difference,
                    "points": row.points,
                    "conduct_score": row.conduct_score,
                }
    fixtures = [
        item
        for item in list_matches(db)
        if item["team_a"] and (item["team_a"]["id"] == team.id or item["team_b"]["id"] == team.id)
    ]
    tournament_id = membership.tournament_id if membership is not None else None
    elo = team_elo(db, tournament_id, team.id) if tournament_id is not None else _latest_rating(db, team.id, "ELO")
    return {
        "id": team.id,
        "slug": team_slug(team.name),
        "fifa_code": team.fifa_code,
        "name": team.name,
        "short_name": team.short_name,
        "confederation": team.confederation,
        "group_code": group_code,
        "is_host": is_host,
        "ratings": {
            "elo": elo,
            "fifa_rank": _latest_fifa_rank(db, team.id),
        },
        "standing": standing,
        "fixtures": fixtures,
        "squad": team_squad(db, team.id),
    }
