from __future__ import annotations

import csv
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from world_cup_api.config import ROOT_DIR
from world_cup_api.db.models import (
    BookmakerOdds,
    BracketSlot,
    Group,
    Match,
    MatchResult,
    PlayerInjury,
    PredictionMarketPrice,
    SquadPlayer,
    Team,
    TeamRating,
    ThirdPlaceAssignment,
    Tournament,
    TournamentTeam,
)
from world_cup_api.domain.bracket import KNOCKOUT_FEEDERS, validate_third_place_matrix


RULESET = "FWC2026-MAY-2026"
SEED_DIR = ROOT_DIR / "data" / "seed"


def seed_database(db: Session) -> None:
    if db.scalar(select(Tournament.id).limit(1)) is not None:
        if db.scalar(select(SquadPlayer.id).limit(1)) is None:
            _seed_squad(db)
            db.commit()
        return
    tournament = Tournament(
        code="FWC2026", name="FIFA World Cup 2026", year=2026,
        starts_on=date(2026, 6, 11), ends_on=date(2026, 7, 19), ruleset_version=RULESET,
    )
    db.add(tournament)
    db.flush()

    team_ids = _seed_draw(db, tournament.id)
    _seed_group_fixtures(db, tournament.id, team_ids)
    db.flush()
    _seed_bracket(db)
    _seed_annex_c(db)
    _seed_ratings(db)
    _seed_results(db)
    _seed_bookmaker_odds(db)
    _seed_prediction_markets(db)
    _seed_squad(db)
    db.commit()


def _read_csv(name: str) -> list[dict[str, str]]:
    path = SEED_DIR / name
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _seed_draw(db: Session, tournament_id: int) -> dict[str, int]:
    team_ids: dict[str, int] = {}
    group_ids: dict[str, int] = {}
    for group_index, code in enumerate("ABCDEFGHIJKL", start=1):
        group = Group(tournament_id=tournament_id, code=code, display_name=f"Group {code}", sort_order=group_index)
        db.add(group)
        db.flush()
        group_ids[code] = group.id

    for row in _read_csv("draw.csv"):
        fifa_code = row["fifa_code"].upper()
        team = Team(
            fifa_code=fifa_code,
            name=row["name"],
            short_name=row["name"],
            country_code=row["country_code"].upper(),
            confederation=row["confederation"].upper(),
        )
        db.add(team)
        db.flush()
        team_ids[fifa_code] = team.id
        db.add(TournamentTeam(
            tournament_id=tournament_id,
            team_id=team.id,
            group_id=group_ids[row["group_code"].upper()],
            draw_position=int(row["draw_position"]),
            is_host=row["is_host"].strip().lower() == "true",
        ))
    return team_ids


def _seed_group_fixtures(db: Session, tournament_id: int, team_ids: dict[str, int]) -> None:
    group_ids = {
        group.code: group.id
        for group in db.scalars(select(Group).where(Group.tournament_id == tournament_id)).all()
    }
    for row in _read_csv("fixtures.csv"):
        db.add(Match(
            tournament_id=tournament_id,
            official_match_number=int(row["match_number"]),
            stage="group",
            group_id=group_ids[row["group_code"].upper()],
            team_a_id=team_ids[row["team_a_fifa_code"].upper()],
            team_b_id=team_ids[row["team_b_fifa_code"].upper()],
            scheduled_at=datetime.fromisoformat(row["scheduled_at"].replace("Z", "+00:00")),
            venue=row.get("venue") or "TBD",
            host_country=row.get("host_country") or "US",
            status=row.get("status") or "scheduled",
        ))


def _seed_ratings(db: Session) -> None:
    for row in _read_csv("ratings.csv"):
        team = db.scalar(select(Team).where(Team.fifa_code == row["fifa_code"].upper()))
        if team is None:
            raise ValueError(f"Unknown team in ratings seed: {row['fifa_code']}")
        db.add(TeamRating(
            team_id=team.id,
            rating_type=row["rating_type"].upper(),
            rating_value=float(row["rating_value"]),
            rank=int(row["rank"]) if row.get("rank", "").strip() else None,
            effective_at=datetime.fromisoformat(row["effective_at"].replace("Z", "+00:00")),
            source=row["source"],
        ))


def _seed_results(db: Session) -> None:
    now = datetime.now(timezone.utc)
    conduct_fields = (
        "team_a_yellows", "team_b_yellows", "team_a_indirect_reds", "team_b_indirect_reds",
        "team_a_direct_reds", "team_b_direct_reds", "team_a_yellow_direct_reds", "team_b_yellow_direct_reds",
    )
    for row in _read_csv("results.csv"):
        match = db.scalar(select(Match).where(Match.official_match_number == int(row["match_number"])))
        if match is None:
            raise ValueError(f"Unknown match in results seed: {row['match_number']}")
        payload = {
            "team_a_goals_90": int(row["team_a_goals_90"]),
            "team_b_goals_90": int(row["team_b_goals_90"]),
            **{field: int(row.get(field) or 0) for field in conduct_fields},
        }
        db.add(MatchResult(
            match_id=match.id,
            revision=1,
            is_current=True,
            recorded_at=now,
            source_updated_at=now,
            source="fifa.com-scores-fixtures",
            **payload,
        ))
        match.status = "final"


def _seed_bookmaker_odds(db: Session) -> None:
    path = SEED_DIR / "bookmaker_odds.csv"
    if not path.exists():
        return
    for row in _read_csv("bookmaker_odds.csv"):
        match = db.scalar(select(Match).where(Match.official_match_number == int(row["match_number"])))
        if match is None:
            raise ValueError(f"Unknown match in bookmaker odds seed: {row['match_number']}")
        db.add(BookmakerOdds(
            match_id=match.id,
            bookmaker=row["bookmaker"],
            market_type=row.get("market_type") or "1X2",
            selection=row["selection"],
            decimal_odds=float(row["decimal_odds"]),
            snapshot_at=datetime.fromisoformat(row["snapshot_at"].replace("Z", "+00:00")),
        ))


def _seed_prediction_markets(db: Session) -> None:
    path = SEED_DIR / "prediction_markets.csv"
    if not path.exists():
        return
    for row in _read_csv("prediction_markets.csv"):
        match = db.scalar(select(Match).where(Match.official_match_number == int(row["match_number"]))) if row.get("match_number") else None
        if match is None:
            raise ValueError(f"Unknown match in prediction market seed: {row['match_number']}")
        db.add(PredictionMarketPrice(
            platform=row["platform"],
            external_market_id=row["external_market_id"],
            contract_id=row["contract_id"],
            market_type=row["market_type"],
            match_id=match.id,
            selection=row["selection"],
            yes_price=float(row["yes_price"]),
            best_bid=float(row["best_bid"]) if row.get("best_bid") else None,
            best_ask=float(row["best_ask"]) if row.get("best_ask") else None,
            volume=float(row["volume"]) if row.get("volume") else None,
            snapshot_at=datetime.fromisoformat(row["snapshot_at"].replace("Z", "+00:00")),
        ))


def _seed_squad(db: Session) -> None:
    from datetime import date as date_type

    squad_path = SEED_DIR / "squad.csv"
    if not squad_path.exists():
        return
    player_by_team_name: dict[tuple[int, str], SquadPlayer] = {}
    for row in _read_csv("squad.csv"):
        team = db.scalar(select(Team).where(Team.fifa_code == row["fifa_code"].upper()))
        if team is None:
            raise ValueError(f"Unknown team in squad seed: {row['fifa_code']}")
        player = SquadPlayer(
            team_id=team.id,
            name=row["name"],
            position=row["position"].upper(),
            squad_number=int(row["squad_number"]),
            fc26_overall=int(row["fc26_overall"]),
            market_value_meur=float(row["market_value_meur"]),
            season_rating_2025_26=float(row["season_rating_2025_26"]) if row.get("season_rating_2025_26") else None,
            season_rating_2024_25=float(row["season_rating_2024_25"]) if row.get("season_rating_2024_25") else None,
            season_rating_2023_24=float(row["season_rating_2023_24"]) if row.get("season_rating_2023_24") else None,
        )
        db.add(player)
        db.flush()
        player_by_team_name[(team.id, row["name"])] = player

    injury_path = SEED_DIR / "player_injuries.csv"
    if not injury_path.exists():
        return
    for row in _read_csv("player_injuries.csv"):
        team = db.scalar(select(Team).where(Team.fifa_code == row["fifa_code"].upper()))
        if team is None:
            raise ValueError(f"Unknown team in injury seed: {row['fifa_code']}")
        player = player_by_team_name.get((team.id, row["player_name"]))
        if player is None:
            raise ValueError(f"Unknown player in injury seed: {row['player_name']}")
        db.add(PlayerInjury(
            player_id=player.id,
            started_on=date_type.fromisoformat(row["started_on"]),
            ended_on=date_type.fromisoformat(row["ended_on"]) if row.get("ended_on") else None,
            days_out=int(row["days_out"]),
        ))


def _seed_bracket(db: Session) -> None:
    round_32 = {
        73: ("group_runner", "A", "group_runner", "B"), 74: ("group_winner", "E", "third_matrix", "74"),
        75: ("group_winner", "F", "group_runner", "C"), 76: ("group_winner", "C", "group_runner", "F"),
        77: ("group_winner", "I", "third_matrix", "77"), 78: ("group_runner", "E", "group_runner", "I"),
        79: ("group_winner", "A", "third_matrix", "79"), 80: ("group_winner", "L", "third_matrix", "80"),
        81: ("group_winner", "D", "third_matrix", "81"), 82: ("group_winner", "G", "third_matrix", "82"),
        83: ("group_runner", "K", "group_runner", "L"), 84: ("group_winner", "H", "group_runner", "J"),
        85: ("group_winner", "B", "third_matrix", "85"), 86: ("group_winner", "J", "group_runner", "H"),
        87: ("group_winner", "K", "third_matrix", "87"), 88: ("group_runner", "D", "group_runner", "G"),
    }
    for number, sources in round_32.items():
        db.add(BracketSlot(ruleset_version=RULESET, official_match_number=number, stage="round_of_32",
                           side_a_source_type=sources[0], side_a_source_ref=sources[1],
                           side_b_source_type=sources[2], side_b_source_ref=sources[3]))
    stages = {range(89, 97): "round_of_16", range(97, 101): "quarterfinal", range(101, 103): "semifinal", range(104, 105): "final"}
    for number, feeders in KNOCKOUT_FEEDERS.items():
        stage = next(value for numbers, value in stages.items() if number in numbers)
        db.add(BracketSlot(ruleset_version=RULESET, official_match_number=number, stage=stage,
                           side_a_source_type="winner", side_a_source_ref=str(feeders[0]),
                           side_b_source_type="winner", side_b_source_ref=str(feeders[1])))
    db.add(BracketSlot(ruleset_version=RULESET, official_match_number=103, stage="third_place",
                       side_a_source_type="loser", side_a_source_ref="101",
                       side_b_source_type="loser", side_b_source_ref="102"))


def _seed_annex_c(db: Session) -> None:
    path = SEED_DIR / "annex_c.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        raw = list(csv.DictReader(handle))
    rows = [(row["qualified_group_set"], int(row["target_match_number"]), row["third_place_group_code"]) for row in raw]
    validate_third_place_matrix(rows)
    db.add_all(ThirdPlaceAssignment(ruleset_version=RULESET, qualified_group_set=group_set,
                                    target_match_number=target, third_place_group_code=group)
               for group_set, target, group in rows)
