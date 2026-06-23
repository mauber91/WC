from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from world_cup_api.db.models import PlayerInjury, SquadPlayer
from world_cup_api.domain.squad_rating import InjuryRecord, composite_rating

POSITION_ORDER = {"GK": 0, "CB": 1, "LB": 2, "RB": 3, "CDM": 4, "CM": 5, "CAM": 6, "LW": 7, "RW": 8, "ST": 9}


def _injury_records(injuries: list[PlayerInjury]) -> list[InjuryRecord]:
    return [
        InjuryRecord(started_on=injury.started_on, ended_on=injury.ended_on, days_out=injury.days_out)
        for injury in injuries
    ]


def _player_dict(player: SquadPlayer, as_of: date | None = None) -> dict:
    injuries = _injury_records(player.injuries)
    rating = composite_rating(
        player.fc26_overall,
        player.market_value_meur,
        player.season_rating_2025_26,
        player.season_rating_2024_25,
        player.season_rating_2023_24,
        injuries,
        as_of,
    )
    lengthy_injuries = [
        {
            "started_on": injury.started_on.isoformat(),
            "ended_on": injury.ended_on.isoformat() if injury.ended_on else None,
            "days_out": injury.days_out,
        }
        for injury in player.injuries
        if injury.days_out >= 14
    ]
    return {
        "id": player.id,
        "name": player.name,
        "position": player.position,
        "squad_number": player.squad_number,
        "fc26_overall": player.fc26_overall,
        "market_value_meur": player.market_value_meur,
        "season_ratings": {
            "2025_26": player.season_rating_2025_26,
            "2024_25": player.season_rating_2024_25,
            "2023_24": player.season_rating_2023_24,
        },
        "rating": rating,
        "lengthy_injuries": lengthy_injuries,
    }


def team_squad(db: Session, team_id: int, as_of: date | None = None) -> list[dict]:
    players = db.scalars(
        select(SquadPlayer)
        .where(SquadPlayer.team_id == team_id)
        .options(selectinload(SquadPlayer.injuries))
    ).all()
    players.sort(key=lambda player: (POSITION_ORDER.get(player.position, 99), player.squad_number))
    return [_player_dict(player, as_of) for player in players]
