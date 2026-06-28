from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from world_cup_api.db.models import BookmakerOdds, Group, Match, PredictionMarketPrice, Team, TeamRating, Tournament
from world_cup_api.domain.host_advantage import venue_home_flags
from world_cup_api.domain.knockout_fixtures import knockout_venues
from world_cup_api.domain.match_context import knockout_rest_context, knockout_venue_coords, travel_km_for_team
from world_cup_api.domain.team_strength import SYNTHETIC_BOOKMAKERS, fuse_strength
from world_cup_api.domain.match_context import group_match_context
from world_cup_api.domain.venues import team_base_camps
from world_cup_api.modeling.context_params import DEFAULT_CONTEXT_PARAMS
from world_cup_api.modeling.pmsr_style import (
    StyleMatchup,
    TacticalStats,
    compute_percentile_bounds,
    ensure_style_model,
    index_style_features_by_match,
    load_team_match_style_features,
    resolve_team_style_profile,
)
from world_cup_api.modeling.pmsr_style import apply_style_to_forecast as apply_style_forecast
from world_cup_api.modeling.prediction import MatchForecast, build_forecast, devig, knockout_win_probability, log_pool
from world_cup_api.services.champion_market_sync import champion_probs_by_team_id
from world_cup_api.services.tournament_elo import current_tournament_elos


@dataclass(frozen=True)
class MatchForecastResult:
    forecast: MatchForecast
    sources: list[dict]
    has_external_market: bool
    match: Match | None = None
    official_match_number: int | None = None
    team_a: Team | None = None
    team_b: Team | None = None
    tactical: TacticalStats | None = None
    style_matchup: StyleMatchup | None = None
    advance_probability_a: float | None = None
    style_profile_a: dict[str, dict[str, float]] | None = None
    style_profile_b: dict[str, dict[str, float]] | None = None


def forecast_match(db: Session, match_id: int) -> MatchForecastResult:
    forecasts = forecast_matches(db, [match_id])
    if match_id not in forecasts:
        raise LookupError("Match not found or teams are not known")
    return forecasts[match_id]


def forecast_knockout_matchup(
    db: Session,
    *,
    official_match_number: int,
    team_a_id: int,
    team_b_id: int,
) -> MatchForecastResult:
    """Forecast a knockout pairing using group-stage PMSR profiles (no future leakage)."""
    team_a = db.get(Team, team_a_id)
    team_b = db.get(Team, team_b_id)
    if team_a is None or team_b is None:
        raise LookupError("One or both teams were not found")
    tournament = db.scalar(select(Tournament).where(Tournament.code == "FWC2026"))
    if tournament is None:
        raise LookupError("Tournament seed data is missing")

    params = DEFAULT_CONTEXT_PARAMS
    style_model = ensure_style_model(db)
    style_features = load_team_match_style_features(db)
    style_by_match = index_style_features_by_match(style_features)
    bounds = style_model.percentile_bounds or compute_percentile_bounds(style_features)
    style_cutoff = _group_stage_style_cutoff(db)
    fifa_ranks = _latest_fifa_ranks(db, {team_a_id, team_b_id}, 50)
    champion_probs = champion_probs_by_team_id(db)
    elos = current_tournament_elos(db, tournament.id)
    host_country = knockout_venues().get(official_match_number, "US")
    host_a, host_b = venue_home_flags(team_a.country_code, team_b.country_code, host_country)
    ctx = _knockout_context(db, official_match_number, team_a, team_b)

    elo_a = fuse_strength(
        elos[team_a_id],
        fifa_ranks.get(team_a_id, 50),
        fifa_weight=params.fifa_strength_weight,
        champion_prob=champion_probs.get(team_a_id),
        champion_weight=params.champion_strength_weight,
        champion_field_size=params.champion_field_size,
    )
    elo_b = fuse_strength(
        elos[team_b_id],
        fifa_ranks.get(team_b_id, 50),
        fifa_weight=params.fifa_strength_weight,
        champion_prob=champion_probs.get(team_b_id),
        champion_weight=params.champion_strength_weight,
        champion_field_size=params.champion_field_size,
    )
    forecast = build_forecast(
        elo_a,
        elo_b,
        host_a=host_a,
        host_b=host_b,
        rest_a=ctx["rest_a"],
        rest_b=ctx["rest_b"],
        travel_a=ctx["travel_a"],
        travel_b=ctx["travel_b"],
        beta_rest=params.beta_rest,
        rest_cap=params.rest_cap_days,
        beta_travel=params.beta_travel,
        travel_ref=params.travel_ref_km,
        goal_dispersion=params.goal_dispersion,
        market_blend_alpha=0.0,
        host_advantage=params.host_advantage_elo,
    )
    profile_a = resolve_team_style_profile(style_features, style_by_match, team_a_id, style_cutoff, bounds)
    profile_b = resolve_team_style_profile(style_features, style_by_match, team_b_id, style_cutoff, bounds)
    profile_payload_a = {"attack": profile_a.attack, "defend": profile_a.defend} if profile_a else None
    profile_payload_b = {"attack": profile_b.attack, "defend": profile_b.defend} if profile_b else None
    tactical: TacticalStats | None = None
    matchup: StyleMatchup | None = None
    if profile_a and profile_b:
        forecast, tactical, matchup = apply_style_forecast(
            forecast,
            profile_a,
            profile_b,
            goal_dispersion=params.goal_dispersion,
            market_blend_alpha=0.0,
            model=style_model,
            team_a_name=team_a.name,
            team_b_name=team_b.name,
        )
    return MatchForecastResult(
        forecast=forecast,
        sources=[],
        has_external_market=False,
        official_match_number=official_match_number,
        team_a=team_a,
        team_b=team_b,
        tactical=tactical,
        style_matchup=matchup,
        advance_probability_a=knockout_win_probability(forecast),
        style_profile_a=profile_payload_a,
        style_profile_b=profile_payload_b,
    )


def forecast_matches(db: Session, match_ids: list[int]) -> dict[int, MatchForecastResult]:
    if not match_ids:
        return {}
    unique_match_ids = list(dict.fromkeys(match_ids))
    matches = db.scalars(select(Match).where(Match.id.in_(unique_match_ids))).all()
    known_matches = [match for match in matches if match.team_a_id is not None and match.team_b_id is not None]
    if not known_matches:
        return {}

    team_ids = {
        team_id
        for match in known_matches
        for team_id in (match.team_a_id, match.team_b_id)
        if team_id is not None
    }
    teams = {team.id: team for team in db.scalars(select(Team).where(Team.id.in_(team_ids))).all()}
    fifa_ranks = _latest_fifa_ranks(db, team_ids, 50)
    champion_probs = champion_probs_by_team_id(db)
    elos_by_tournament = {
        tournament_id: current_tournament_elos(db, tournament_id)
        for tournament_id in {match.tournament_id for match in known_matches}
    }
    markets = _market_consensus_by_match(db, unique_match_ids)
    contexts = _group_match_contexts(db, known_matches)
    params = DEFAULT_CONTEXT_PARAMS
    style_model = ensure_style_model(db)
    style_features = load_team_match_style_features(db)
    style_by_match = index_style_features_by_match(style_features)
    bounds = style_model.percentile_bounds or compute_percentile_bounds(style_features)
    style_cutoff = _group_stage_style_cutoff(db)
    output: dict[int, MatchForecastResult] = {}

    for match in known_matches:
        team_a = teams.get(match.team_a_id)
        team_b = teams.get(match.team_b_id)
        if team_a is None or team_b is None:
            continue
        elo_table = elos_by_tournament[match.tournament_id]
        elo_a = fuse_strength(
            elo_table[match.team_a_id],
            fifa_ranks.get(match.team_a_id, 50),
            fifa_weight=params.fifa_strength_weight,
            champion_prob=champion_probs.get(match.team_a_id),
            champion_weight=params.champion_strength_weight,
            champion_field_size=params.champion_field_size,
        )
        elo_b = fuse_strength(
            elo_table[match.team_b_id],
            fifa_ranks.get(match.team_b_id, 50),
            fifa_weight=params.fifa_strength_weight,
            champion_prob=champion_probs.get(match.team_b_id),
            champion_weight=params.champion_strength_weight,
            champion_field_size=params.champion_field_size,
        )
        market, sources, has_external_market = markets.get(match.id, (None, [], False))
        host_a, host_b = venue_home_flags(team_a.country_code, team_b.country_code, match.host_country)
        ctx = contexts.get(match.id, {})
        blend_alpha = params.market_blend_alpha if has_external_market else 0.0
        forecast = build_forecast(
            elo_a, elo_b, market, host_a, host_b,
            rest_a=ctx.get("rest_a", 0.0),
            rest_b=ctx.get("rest_b", 0.0),
            travel_a=ctx.get("travel_a", 0.0),
            travel_b=ctx.get("travel_b", 0.0),
            beta_rest=params.beta_rest,
            rest_cap=params.rest_cap_days,
            beta_travel=params.beta_travel,
            travel_ref=params.travel_ref_km,
            goal_dispersion=params.goal_dispersion,
            market_blend_alpha=blend_alpha,
            host_advantage=params.host_advantage_elo,
        )
        profile_before = style_cutoff if match.group_id is None else match.official_match_number
        profile_a = resolve_team_style_profile(
            style_features, style_by_match, match.team_a_id, profile_before, bounds
        )
        profile_b = resolve_team_style_profile(
            style_features, style_by_match, match.team_b_id, profile_before, bounds
        )
        profile_payload_a = {"attack": profile_a.attack, "defend": profile_a.defend} if profile_a else None
        profile_payload_b = {"attack": profile_b.attack, "defend": profile_b.defend} if profile_b else None
        if profile_a and profile_b:
            forecast, tactical, matchup = apply_style_forecast(
                forecast,
                profile_a,
                profile_b,
                goal_dispersion=params.goal_dispersion,
                market_blend_alpha=blend_alpha,
                model=style_model,
                team_a_name=team_a.name,
                team_b_name=team_b.name,
            )
        else:
            tactical, matchup = None, None
        advance = None
        if match.group_id is None:
            advance = knockout_win_probability(forecast)
        output[match.id] = MatchForecastResult(
            match=match,
            forecast=forecast,
            sources=sources,
            has_external_market=has_external_market,
            tactical=tactical,
            style_matchup=matchup,
            advance_probability_a=advance,
            style_profile_a=profile_payload_a,
            style_profile_b=profile_payload_b,
        )
    return output


def _group_stage_style_cutoff(db: Session) -> int:
    """Use every completed group-stage PMSR report when profiling knockout teams."""
    max_number = db.scalar(select(func.max(Match.official_match_number)).where(Match.group_id.is_not(None)))
    return int(max_number or 72) + 1


def _group_matches_for_knockout_context(db: Session) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for group in db.scalars(select(Group).order_by(Group.sort_order)):
        rows = db.scalars(
            select(Match).where(Match.group_id == group.id).order_by(Match.scheduled_at)
        ).all()
        groups[group.code] = [
            {
                "id": row.id,
                "a": row.team_a_id,
                "b": row.team_b_id,
                "scheduled_at": row.scheduled_at,
                "venue": row.venue,
            }
            for row in rows
        ]
    return groups


def _knockout_context(
    db: Session,
    official_match_number: int,
    team_a: Team,
    team_b: Team,
) -> dict[str, float]:
    rest_map = knockout_rest_context(_group_matches_for_knockout_context(db))
    rest_a, rest_b = rest_map.get(official_match_number, (0.0, 0.0))
    venue_coords = knockout_venue_coords().get(official_match_number)
    camps = team_base_camps()
    camp_a = camps.get(team_a.fifa_code)
    camp_b = camps.get(team_b.fifa_code)
    travel_a = (
        travel_km_for_team((camp_a.lat, camp_a.lon), tuple(venue_coords))
        if venue_coords is not None and camp_a is not None
        else 0.0
    )
    travel_b = (
        travel_km_for_team((camp_b.lat, camp_b.lon), tuple(venue_coords))
        if venue_coords is not None and camp_b is not None
        else 0.0
    )
    return {"rest_a": rest_a, "rest_b": rest_b, "travel_a": travel_a, "travel_b": travel_b}


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


def _latest_fifa_ranks(db: Session, team_ids: set[int], default: float) -> dict[int, float]:
    rows = db.scalars(select(TeamRating).where(
        TeamRating.team_id.in_(team_ids),
        TeamRating.rating_type == "FIFA_RANK",
        TeamRating.effective_at <= datetime.now(timezone.utc),
    ).order_by(TeamRating.team_id, TeamRating.effective_at.desc())).all()
    latest: dict[int, float] = {}
    for row in rows:
        if row.team_id not in latest:
            latest[row.team_id] = float(row.rank if row.rank is not None else row.rating_value)
    return {team_id: latest.get(team_id, default) for team_id in team_ids}


def _market_consensus(db: Session, match_id: int) -> tuple[tuple[float, float, float] | None, list[dict], bool]:
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
        if book in SYNTHETIC_BOOKMAKERS:
            continue
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
        return None, [], False
    return log_pool(family_vectors, family_weights), sources, True  # type: ignore[return-value]


def _group_match_contexts(db: Session, matches: list[Match]) -> dict[int, dict[str, float]]:
    group_ids = {match.group_id for match in matches if match.group_id is not None}
    if not group_ids:
        return {}
    group_matches = db.scalars(
        select(Match).where(Match.group_id.in_(group_ids)).order_by(Match.group_id, Match.scheduled_at)
    ).all()
    team_ids = {
        team_id
        for row in group_matches
        for team_id in (row.team_a_id, row.team_b_id)
        if team_id is not None
    }
    teams = db.scalars(select(Team).where(Team.id.in_(team_ids))).all()
    fifa_by_id = {team.id: team.fifa_code for team in teams}
    by_group: dict[int, list[dict]] = defaultdict(list)
    for row in group_matches:
        if row.group_id is None:
            continue
        by_group[row.group_id].append({
            "id": row.id,
            "a": row.team_a_id,
            "b": row.team_b_id,
            "scheduled_at": row.scheduled_at,
            "venue": row.venue,
        })
    contexts: dict[int, dict[str, float]] = {}
    for group_rows in by_group.values():
        contexts.update(group_match_context(group_rows, fifa_by_id))
    return contexts


def _market_consensus_by_match(
    db: Session,
    match_ids: list[int],
) -> dict[int, tuple[tuple[float, float, float] | None, list[dict], bool]]:
    bookmaker_rows = db.scalars(select(BookmakerOdds).where(
        BookmakerOdds.match_id.in_(match_ids),
        BookmakerOdds.market_type == "1X2",
    ).order_by(BookmakerOdds.match_id, BookmakerOdds.snapshot_at.desc())).all()
    market_rows = db.scalars(select(PredictionMarketPrice).where(
        PredictionMarketPrice.match_id.in_(match_ids),
        PredictionMarketPrice.market_type == "1X2",
    ).order_by(PredictionMarketPrice.match_id, PredictionMarketPrice.snapshot_at.desc())).all()

    bookmaker_groups: dict[int, dict[tuple[str, datetime], dict[str, BookmakerOdds]]] = defaultdict(lambda: defaultdict(dict))
    for row in bookmaker_rows:
        bookmaker_groups[row.match_id][(row.bookmaker, row.snapshot_at)][row.selection] = row

    prediction_groups: dict[int, dict[tuple[str, str, datetime], dict[str, PredictionMarketPrice]]] = defaultdict(lambda: defaultdict(dict))
    for row in market_rows:
        if row.match_id is None:
            continue
        prediction_groups[row.match_id][(row.platform, row.external_market_id, row.snapshot_at)][row.selection] = row

    output: dict[int, tuple[tuple[float, float, float] | None, list[dict], bool]] = {}
    for match_id in match_ids:
        family_vectors: list[tuple[float, float, float]] = []
        family_weights: list[float] = []
        sources: list[dict] = []
        vectors: list[tuple[float, float, float]] = []
        seen_books: set[str] = set()
        for (book, timestamp), selections in bookmaker_groups.get(match_id, {}).items():
            if book in SYNTHETIC_BOOKMAKERS:
                continue
            if book in seen_books or not all(key in selections for key in ("team_a", "draw", "team_b")):
                continue
            odds = [selections[key].decimal_odds for key in ("team_a", "draw", "team_b")]
            vector = devig(odds)
            vectors.append(vector)  # type: ignore[arg-type]
            sources.append({"bookmaker": book, "snapshot_at": timestamp, "decimal_odds": odds, "devigged": vector})
            seen_books.add(book)
        if vectors:
            family_vectors.append(log_pool(vectors, [1.0] * len(vectors)))  # type: ignore[arg-type]
            family_weights.append(0.6)

        seen_platforms: set[str] = set()
        for (platform, market_id, timestamp), selections in prediction_groups.get(match_id, {}).items():
            if platform in seen_platforms or not all(key in selections for key in ("team_a", "draw", "team_b")):
                continue
            raw = []
            for key in ("team_a", "draw", "team_b"):
                row = selections[key]
                raw.append((row.best_bid + row.best_ask) / 2 if row.best_bid is not None and row.best_ask is not None else row.yes_price)
            total = sum(raw)
            if total <= 0:
                continue
            vector = tuple(value / total for value in raw)
            family_vectors.append(vector)  # type: ignore[arg-type]
            family_weights.append(0.2)
            sources.append({"platform": platform, "external_market_id": market_id, "snapshot_at": timestamp,
                            "normalized_prices": vector})
            seen_platforms.add(platform)
        if family_vectors:
            output[match_id] = (log_pool(family_vectors, family_weights), sources, True)  # type: ignore[arg-type]
        else:
            output[match_id] = (None, [], False)
    return output
