from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from world_cup_api.db.models import Match, PredictionMarketPrice, Team
from world_cup_api.ingestion.attena import AttenaMarketResult, search_markets
from world_cup_api.ingestion.kalshi import KalshiMarketQuote, fetch_event_markets


TEAM_SEARCH_ALIASES: dict[str, tuple[str, ...]] = {
    "CIV": ("Ivory Coast", "Côte d'Ivoire", "Cote d'Ivoire"),
    "KOR": ("Korea Republic", "South Korea"),
    "USA": ("United States", "USA"),
    "TUR": ("Türkiye", "Turkey"),
    "CPV": ("Cabo Verde", "Cape Verde"),
    "COD": ("Congo DR", "DR Congo"),
    "CUW": ("Curaçao", "Curacao"),
}


@dataclass(frozen=True)
class MarketQuote:
    platform: str
    external_market_id: str
    contract_id: str
    selection: str
    yes_price: float
    best_bid: float | None
    best_ask: float | None
    volume: float | None
    source_url: str | None


@dataclass(frozen=True)
class MatchSyncReport:
    match_id: int
    match_number: int
    queries: tuple[str, ...]
    attena_hits: int
    stored_rows: int
    platforms: tuple[str, ...]
    warnings: tuple[str, ...]


def sync_upcoming_markets(db: Session, *, match_numbers: list[int] | None = None) -> list[MatchSyncReport]:
    matches = db.scalars(
        select(Match)
        .where(Match.stage == "group", Match.status != "final")
        .order_by(Match.official_match_number)
    ).all()
    if match_numbers is not None:
        wanted = set(match_numbers)
        matches = [match for match in matches if match.official_match_number in wanted]
    reports: list[MatchSyncReport] = []
    for match in matches:
        if match.team_a_id is None or match.team_b_id is None:
            continue
        team_a = db.get(Team, match.team_a_id)
        team_b = db.get(Team, match.team_b_id)
        if team_a is None or team_b is None:
            continue
        reports.append(_sync_match(db, match, team_a, team_b))
    db.commit()
    return reports


def _sync_match(db: Session, match: Match, team_a: Team, team_b: Team) -> MatchSyncReport:
    queries = _build_queries(team_a, team_b, match.scheduled_at)
    attena_results: dict[tuple[str, str], AttenaMarketResult] = {}
    warnings: list[str] = []
    for query in queries:
        try:
            for result in search_markets(query):
                if not _result_matches_match(result, team_a, team_b, match.scheduled_at):
                    continue
                attena_results[(result.source, result.market_id)] = result
        except RuntimeError as exc:
            warnings.append(str(exc))

    quotes = _quotes_from_attena(attena_results.values(), team_a, team_b, warnings)
    quotes.extend(_quotes_from_kalshi_enrichment(attena_results.values(), team_a, team_b, warnings))

    deduped = _dedupe_quotes(quotes)
    snapshot_at = datetime.now(timezone.utc)
    stored = 0
    platforms: set[str] = set()
    for quote in deduped:
        db.add(PredictionMarketPrice(
            platform=quote.platform,
            external_market_id=quote.external_market_id,
            contract_id=quote.contract_id,
            market_type="1X2",
            match_id=match.id,
            selection=quote.selection,
            yes_price=quote.yes_price,
            best_bid=quote.best_bid,
            best_ask=quote.best_ask,
            volume=quote.volume,
            snapshot_at=snapshot_at,
        ))
        stored += 1
        platforms.add(quote.platform)

    return MatchSyncReport(
        match_id=match.id,
        match_number=match.official_match_number,
        queries=queries,
        attena_hits=len(attena_results),
        stored_rows=stored,
        platforms=tuple(sorted(platforms)),
        warnings=tuple(warnings),
    )


def _build_queries(team_a: Team, team_b: Team, scheduled_at: datetime) -> tuple[str, ...]:
    date_label = scheduled_at.date().isoformat()
    head_to_head = f"FIFA World Cup {team_a.name} vs {team_b.name}"
    return (
        f"{head_to_head} {date_label}",
        f"{head_to_head} tie",
        f"{head_to_head} {team_b.name}",
        f"{team_a.name} {team_b.name} World Cup {date_label}",
    )


def _result_matches_match(result: AttenaMarketResult, team_a: Team, team_b: Team, scheduled_at: datetime) -> bool:
    if result.source not in {"kalshi", "polymarket"}:
        return False
    haystack = result.title.lower()
    if not (_name_in_text(team_a, haystack) and _name_in_text(team_b, haystack)):
        return False
    if result.subcategory not in {None, "world_cup", "soccer"} and result.league not in {None, "FIFA World Cup", "World Cup"}:
        if "world cup" not in haystack and "fifa" not in haystack:
            return False
    if result.event_date:
        if result.event_date[:10] != scheduled_at.date().isoformat():
            return False
    return True


def _quotes_from_attena(results: list[AttenaMarketResult], team_a: Team, team_b: Team,
                          warnings: list[str]) -> list[MarketQuote]:
    quotes: list[MarketQuote] = []
    for result in results:
        selection = _map_selection(result.outcome_label or result.title, team_a, team_b)
        if selection is None:
            continue
        quotes.append(MarketQuote(
            platform=result.source,
            external_market_id=_event_id(result),
            contract_id=result.market_id,
            selection=selection,
            yes_price=result.yes_price,
            best_bid=max(result.yes_price - 0.02, 0.0),
            best_ask=min(result.yes_price + 0.02, 1.0),
            volume=result.volume_24h or result.volume,
            source_url=result.source_url,
        ))
    if not quotes:
        warnings.append("No Attena results mapped to 1X2 selections")
    return quotes


def _quotes_from_kalshi_enrichment(results: list[AttenaMarketResult], team_a: Team, team_b: Team,
                                   warnings: list[str]) -> list[MarketQuote]:
    event_tickers = {
        _kalshi_event_ticker(result.market_id)
        for result in results
        if result.source == "kalshi"
    }
    event_tickers.discard("")
    quotes: list[MarketQuote] = []
    for event_ticker in sorted(event_tickers):
        try:
            kalshi_markets = fetch_event_markets(event_ticker)
        except RuntimeError as exc:
            warnings.append(str(exc))
            continue
        quotes.extend(_quotes_from_kalshi_markets(kalshi_markets, team_a, team_b))
    return quotes


def _quotes_from_kalshi_markets(markets: list[KalshiMarketQuote], team_a: Team, team_b: Team) -> list[MarketQuote]:
    if not markets:
        return []
    raw: dict[str, float] = {}
    meta: dict[str, KalshiMarketQuote] = {}
    for market in markets:
        selection = _map_selection(market.outcome_label, team_a, team_b)
        if selection is None:
            continue
        raw[selection] = market.yes_price
        meta[selection] = market
    normalized = _normalize_three_way(raw)
    quotes: list[MarketQuote] = []
    for selection, yes_price in normalized.items():
        market = meta[selection]
        quotes.append(MarketQuote(
            platform="kalshi",
            external_market_id=market.event_ticker,
            contract_id=market.ticker,
            selection=selection,
            yes_price=yes_price,
            best_bid=market.best_bid,
            best_ask=market.best_ask,
            volume=market.volume,
            source_url=f"https://kalshi.com/markets/{market.event_ticker.lower()}",
        ))
    return quotes


def _map_selection(label: str, team_a: Team, team_b: Team) -> str | None:
    normalized = label.strip().lower()
    if normalized in {"tie", "draw"}:
        return "draw"
    if _label_matches_team(normalized, team_a):
        return "team_a"
    if _label_matches_team(normalized, team_b):
        return "team_b"
    return None


def _label_matches_team(label: str, team: Team) -> bool:
    names = (team.name, team.short_name, team.fifa_code, *TEAM_SEARCH_ALIASES.get(team.fifa_code, ()))
    return any(name and name.lower() in label or label in name.lower() for name in names)


def _name_in_text(team: Team, text: str) -> bool:
    names = (team.name, team.short_name, *TEAM_SEARCH_ALIASES.get(team.fifa_code, ()))
    return any(name.lower() in text for name in names if name)


def _event_id(result: AttenaMarketResult) -> str:
    if result.source == "kalshi":
        return _kalshi_event_ticker(result.market_id) or result.market_id
    match = re.search(r"/market/([^/?#]+)", result.source_url or "")
    return match.group(1) if match else result.market_id


def _kalshi_event_ticker(market_id: str) -> str:
    if "-" not in market_id:
        return market_id
    return market_id.rsplit("-", 1)[0]


def _normalize_three_way(raw: dict[str, float]) -> dict[str, float]:
    if not raw:
        return {}
    total = sum(max(value, 0.0) for value in raw.values())
    if total <= 0:
        return raw
    return {key: value / total for key, value in raw.items()}


def _dedupe_quotes(quotes: list[MarketQuote]) -> list[MarketQuote]:
    best: dict[tuple[str, str], MarketQuote] = {}
    for quote in quotes:
        key = (quote.platform, quote.selection)
        current = best.get(key)
        if current is None or quote.yes_price > current.yes_price:
            best[key] = quote
    return list(best.values())
