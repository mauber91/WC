from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from world_cup_api.db.models import Group, Match, MatchResult, Team, TeamRating, TournamentTeam
from world_cup_api.domain.standings import MatchRecord, RankedTable, StandingRow, calculate_group_table, rank_third_place


def group_list(db: Session) -> list[dict]:
    groups = db.scalars(select(Group).order_by(Group.sort_order)).all()
    members = db.execute(
        select(TournamentTeam.group_id, Team.id, Team.fifa_code, Team.name)
        .join(Team, Team.id == TournamentTeam.team_id)
        .order_by(TournamentTeam.group_id, TournamentTeam.draw_position)
    ).all()
    members_by_group: dict[int, list[dict]] = {}
    for row in members:
        members_by_group.setdefault(row.group_id, []).append({
            "id": row.id,
            "fifa_code": row.fifa_code,
            "name": row.name,
        })
    result = []
    for group in groups:
        result.append({"id": group.id, "code": group.code, "display_name": group.display_name,
                       "teams": members_by_group.get(group.id, [])})
    return result


def group_standings(db: Session, code: str) -> tuple[Group, RankedTable]:
    group = db.scalar(select(Group).where(Group.code == code.upper()))
    if group is None:
        raise LookupError(f"Unknown group {code}")
    members = db.execute(
        select(Team.id, Team.name)
        .join(TournamentTeam, TournamentTeam.team_id == Team.id)
        .where(TournamentTeam.group_id == group.id)
    ).all()
    rank_history = _fifa_rank_history(db, [row.id for row in members])
    rows = [StandingRow(team_id=row.id, name=row.name, fifa_rank_history=rank_history.get(row.id, ())) for row in members]
    matches = db.scalars(select(Match).where(Match.group_id == group.id)).all()
    results = {
        result.match_id: result
        for result in db.scalars(
            select(MatchResult).where(
                MatchResult.match_id.in_([match.id for match in matches]),
                MatchResult.is_current.is_(True),
            )
        ).all()
    }
    records: list[MatchRecord] = []
    for match in matches:
        result = results.get(match.id)
        if result is None or match.team_a_id is None or match.team_b_id is None:
            continue
        records.append(MatchRecord(match.team_a_id, match.team_b_id, result.team_a_goals_90,
                                   result.team_b_goals_90, result.conduct_a, result.conduct_b))
    table = calculate_group_table(rows, records)
    if any(_rating_sources_provisional(db, [row.team_id for row in rows]).values()):
        warnings = table.warnings + ("FIFA rankings are provisional; import an official ranking edition.",)
        table = RankedTable(table.rows, True, tuple(dict.fromkeys(warnings)))
    return group, table


def current_third_place(db: Session) -> RankedTable:
    third_rows = [group_standings(db, group.code)[1].rows[2] for group in db.scalars(select(Group).order_by(Group.sort_order))]
    return rank_third_place(third_rows)


def list_matches(db: Session, group_code: str | None = None) -> list[dict]:
    query = select(Match).options(
        selectinload(Match.group),
        selectinload(Match.team_a),
        selectinload(Match.team_b),
    ).order_by(Match.official_match_number)
    if group_code:
        query = query.join(Group).where(Group.code == group_code.upper())
    matches = db.scalars(query).all()
    results = {
        result.match_id: result
        for result in db.scalars(
            select(MatchResult).where(
                MatchResult.match_id.in_([match.id for match in matches]),
                MatchResult.is_current.is_(True),
            )
        ).all()
    }
    output = []
    for match in matches:
        result = results.get(match.id)
        output.append({
            "id": match.id, "official_match_number": match.official_match_number, "stage": match.stage,
            "group_code": match.group.code if match.group else None,
            "team_a": {"id": match.team_a.id, "name": match.team_a.name, "fifa_code": match.team_a.fifa_code} if match.team_a else None,
            "team_b": {"id": match.team_b.id, "name": match.team_b.name, "fifa_code": match.team_b.fifa_code} if match.team_b else None,
            "scheduled_at": match.scheduled_at, "status": match.status,
            "host_country": match.host_country,
            "result": {"team_a_goals": result.team_a_goals_90, "team_b_goals": result.team_b_goals_90,
                       "revision": result.revision} if result else None,
        })
    return output


def _fifa_rank_history(db: Session, team_ids: list[int]) -> dict[int, tuple[int, ...]]:
    ratings = db.scalars(
        select(TeamRating).where(TeamRating.team_id.in_(team_ids), TeamRating.rating_type == "FIFA_RANK")
        .order_by(TeamRating.team_id, TeamRating.effective_at.desc())
    ).all()
    history: dict[int, list[int]] = {}
    for rating in ratings:
        history.setdefault(rating.team_id, []).append(rating.rank or int(rating.rating_value))
    return {team_id: tuple(values) for team_id, values in history.items()}


def _rating_sources_provisional(db: Session, team_ids: list[int]) -> dict[int, bool]:
    ratings = db.scalars(
        select(TeamRating).where(
            TeamRating.team_id.in_(team_ids),
            TeamRating.rating_type == "FIFA_RANK",
        ).order_by(TeamRating.team_id, TeamRating.effective_at.desc())
    ).all()
    sources: dict[int, str] = {}
    for rating in ratings:
        if rating.team_id not in sources:
            sources[rating.team_id] = rating.source
    return {team_id: sources.get(team_id) == "seed-provisional" for team_id in team_ids}
