from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from world_cup_api.db.models import BookmakerOdds, Match, PredictionMarketPrice, Team, TeamRating
from world_cup_api.domain.host_advantage import venue_home_flags
from world_cup_api.domain.match_context import group_match_context
from world_cup_api.modeling.context_params import DEFAULT_CONTEXT_PARAMS
from world_cup_api.modeling.prediction import MatchForecast, build_forecast, devig, log_pool
from world_cup_api.services.tournament_elo import team_elo


def _group_match_context(db: Session, match: Match) -> dict[str, float]:
    if match.group_id is None:
        return {}
    group_matches = db.scalars(
        select(Match).where(Match.group_id == match.group_id).order_by(Match.scheduled_at)
    ).all()
    team_ids = {row.team_a_id for row in group_matches} | {row.team_b_id for row in group_matches}
    teams = db.scalars(select(Team).where(Team.id.in_(team_ids))).all()
    fifa_by_id = {team.id: team.fifa_code for team in teams}
    payload = [
        {"id": row.id, "a": row.team_a_id, "b": row.team_b_id, "scheduled_at": row.scheduled_at, "venue": row.venue}
        for row in group_matches
    ]
    return group_match_context(payload, fifa_by_id).get(match.id, {})


def forecast_match(db: Session, match_id: int) -> tuple[Match, MatchForecast, list[dict]]:
    match = db.get(Match, match_id)
    if match is None or match.team_a_id is None or match.team_b_id is None:
        raise LookupError("Match not found or teams are not known")
    team_a = db.get(Team, match.team_a_id)
    team_b = db.get(Team, match.team_b_id)
    if team_a is None or team_b is None:
        raise LookupError("Match teams are not known")
    elo_a = team_elo(db, match.tournament_id, match.team_a_id)
    elo_b = team_elo(db, match.tournament_id, match.team_b_id)
    rank_a = _latest_fifa_rank(db, match.team_a_id, 50)
    rank_b = _latest_fifa_rank(db, match.team_b_id, 50)
    market, sources = _market_consensus(db, match_id)
    host_a, host_b = venue_home_flags(team_a.country_code, team_b.country_code, match.host_country)
    ctx = _group_match_context(db, match)
    params = DEFAULT_CONTEXT_PARAMS
    return match, build_forecast(
        elo_a, elo_b, market, host_a, host_b,
        fifa_z_a=(50 - rank_a) / 15, fifa_z_b=(50 - rank_b) / 15,
        rest_a=ctx.get("rest_a", 0.0),
        rest_b=ctx.get("rest_b", 0.0),
        travel_a=ctx.get("travel_a", 0.0),
        travel_b=ctx.get("travel_b", 0.0),
        beta_rest=params.beta_rest,
        rest_cap=params.rest_cap_days,
        beta_travel=params.beta_travel,
        travel_ref=params.travel_ref_km,
        goal_dispersion=params.goal_dispersion,
    ), sources


def _latest_rating(db: Session, team_id: int, kind: str, default: float) -> float:
    value = db.scalar(select(TeamRating.rating_value).where(TeamRating.team_id == team_id,
                                                             TeamRating.rating_type == kind,
                                                             TeamRating.effective_at <= datetime.now(timezone.utc))
                      .order_by(TeamRating.effective_at.desc()).limit(1))
    return float(value if value is not None else default)


def _latest_fifa_rank(db: Session, team_id: int, default: float) -> float:
    rating = db.scalar(select(TeamRating).where(TeamRating.team_id == team_id,
                                                 TeamRating.rating_type == "FIFA_RANK",
                                                 TeamRating.effective_at <= datetime.now(timezone.utc))
                       .order_by(TeamRating.effective_at.desc()).limit(1))
    if rating is None:
        return default
    return float(rating.rank if rating.rank is not None else rating.rating_value)


def _market_consensus(db: Session, match_id: int) -> tuple[tuple[float, float, float] | None, list[dict]]:
    rows = db.scalars(select(BookmakerOdds).where(BookmakerOdds.match_id == match_id,
                                                   BookmakerOdds.market_type == "1X2")
                      .order_by(BookmakerOdds.snapshot_at.desc())).all()
    grouped: dict[tuple[str, datetime], dict[str, BookmakerOdds]] = defaultdict(dict)
    for row in rows:
        grouped[(row.bookmaker, row.snapshot_at)][row.selection] = row
    vectors: list[tuple[float, float, float]] = []
    sources: list[dict] = []
    seen_books: set[str] = set()
    for (book, timestamp), selections in grouped.items():
        if book in seen_books or not all(key in selections for key in ("team_a", "draw", "team_b")):
            continue
        odds = [selections[key].decimal_odds for key in ("team_a", "draw", "team_b")]
        vector = devig(odds)
        vectors.append(vector)  # type: ignore[arg-type]
        sources.append({"bookmaker": book, "snapshot_at": timestamp, "decimal_odds": odds, "devigged": vector})
        seen_books.add(book)
    family_vectors: list[tuple[float, float, float]] = []
    family_weights: list[float] = []
    if vectors:
        family_vectors.append(log_pool(vectors, [1.0] * len(vectors)))  # type: ignore[arg-type]
        family_weights.append(0.6)

    market_rows = db.scalars(select(PredictionMarketPrice).where(
        PredictionMarketPrice.match_id == match_id, PredictionMarketPrice.market_type == "1X2",
    ).order_by(PredictionMarketPrice.snapshot_at.desc())).all()
    market_groups: dict[tuple[str, str, datetime], dict[str, PredictionMarketPrice]] = defaultdict(dict)
    for row in market_rows:
        market_groups[(row.platform, row.external_market_id, row.snapshot_at)][row.selection] = row
    seen_platforms: set[str] = set()
    for (platform, market_id, timestamp), selections in market_groups.items():
        if platform in seen_platforms or not all(key in selections for key in ("team_a", "draw", "team_b")):
            continue
        raw = []
        for key in ("team_a", "draw", "team_b"):
            row = selections[key]
            raw.append((row.best_bid + row.best_ask) / 2 if row.best_bid is not None and row.best_ask is not None else row.yes_price)
        total = sum(raw)
        vector = tuple(value / total for value in raw)
        family_vectors.append(vector)  # type: ignore[arg-type]
        family_weights.append(0.2)
        sources.append({"platform": platform, "external_market_id": market_id, "snapshot_at": timestamp,
                        "normalized_prices": vector})
        seen_platforms.add(platform)
    if not family_vectors:
        return None, []
    return log_pool(family_vectors, family_weights), sources  # type: ignore[return-value]
