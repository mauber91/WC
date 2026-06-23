from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from world_cup_api.config import get_settings
from world_cup_api.db.models import Team, TeamRating, Tournament, TournamentTeam
from world_cup_api.domain.champion_markets import (
    WC_CHAMPION_RATING_TYPE,
    build_fifa_label_index,
    match_champion_label,
    normalize_champion_probabilities,
    pool_champion_probability,
)
from world_cup_api.ingestion.kalshi import fetch_event_markets
from world_cup_api.ingestion.polymarket import fetch_wc_winner_quotes


@dataclass(frozen=True)
class ChampionSyncReport:
    teams_matched: int
    stored_rows: int
    platforms: tuple[str, ...]
    top_favorites: tuple[tuple[str, float], ...]
    warnings: tuple[str, ...]


def sync_wc_champion_markets(db: Session) -> ChampionSyncReport:
    settings = get_settings()
    warnings: list[str] = []
    teams = _tournament_teams(db)
    if not teams:
        return ChampionSyncReport(0, 0, (), (), ("No tournament teams found",))

    label_index = build_fifa_label_index(teams)
    by_code: dict[str, dict[str, float]] = {}

    try:
        for quote in fetch_wc_winner_quotes():
            code = match_champion_label(quote.team_label, label_index)
            if code is None:
                continue
            by_code.setdefault(code, {})[quote.platform] = quote.yes_price
    except RuntimeError as exc:
        warnings.append(str(exc))

    try:
        for row in fetch_event_markets(settings.kalshi_wc_winner_event):
            code = match_champion_label(row.outcome_label, label_index)
            if code is None:
                continue
            by_code.setdefault(code, {})["kalshi"] = row.yes_price
    except RuntimeError as exc:
        warnings.append(str(exc))

    pooled: dict[str, float] = {}
    for code, platform_prices in by_code.items():
        prob = pool_champion_probability(list(platform_prices.values()))
        if prob is not None:
            pooled[code] = prob

    pooled = normalize_champion_probabilities(pooled)
    team_by_code = {team.fifa_code: team for team in teams}
    snapshot_at = datetime.now(timezone.utc)
    stored = 0
    platforms: set[str] = set()

    for code, probability in pooled.items():
        team = team_by_code.get(code)
        if team is None:
            continue
        db.add(TeamRating(
            team_id=team.id,
            rating_type=WC_CHAMPION_RATING_TYPE,
            rating_value=probability,
            rank=None,
            attack_rating=None,
            defense_rating=None,
            effective_at=snapshot_at,
            source="consensus",
            source_ref=f"polymarket+kalshi:{settings.kalshi_wc_winner_event}",
        ))
        stored += 1
        for platform in by_code.get(code, {}):
            platforms.add(platform)

    for code, platform_prices in by_code.items():
        team = team_by_code.get(code)
        if team is None:
            continue
        for platform, probability in platform_prices.items():
            db.add(TeamRating(
                team_id=team.id,
                rating_type=WC_CHAMPION_RATING_TYPE,
                rating_value=probability,
                rank=None,
                attack_rating=None,
                defense_rating=None,
                effective_at=snapshot_at,
                source=platform,
                source_ref=settings.kalshi_wc_winner_event if platform == "kalshi" else "world-cup-winner",
            ))
            stored += 1

    db.commit()
    top = tuple(
        sorted(((code, prob) for code, prob in pooled.items()), key=lambda item: item[1], reverse=True)[:5]
    )
    return ChampionSyncReport(
        teams_matched=len(pooled),
        stored_rows=stored,
        platforms=tuple(sorted(platforms)),
        top_favorites=top,
        warnings=tuple(warnings),
    )


def champion_probs_by_team_id(db: Session) -> dict[int, float]:
    rows = db.scalars(
        select(TeamRating)
        .where(
            TeamRating.rating_type == WC_CHAMPION_RATING_TYPE,
            TeamRating.source == "consensus",
            TeamRating.effective_at <= datetime.now(timezone.utc),
        )
        .order_by(TeamRating.team_id, TeamRating.effective_at.desc())
    ).all()
    latest: dict[int, float] = {}
    for row in rows:
        if row.team_id not in latest:
            latest[row.team_id] = float(row.rating_value)
    return latest


def _tournament_teams(db: Session) -> list[Team]:
    tournament = db.scalar(select(Tournament).where(Tournament.code == "FWC2026"))
    if tournament is None:
        return []
    return list(db.scalars(
        select(Team)
        .join(TournamentTeam, TournamentTeam.team_id == Team.id)
        .where(TournamentTeam.tournament_id == tournament.id)
    ).all())
