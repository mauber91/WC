from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from world_cup_api.config import get_settings
from world_cup_api.domain.champion_markets import ChampionQuote, parse_polymarket_team_label


@dataclass(frozen=True)
class PolymarketChampionQuote:
    event_slug: str
    market_id: str
    question: str
    team_label: str
    yes_price: float


def fetch_wc_winner_quotes(*, event_slug: str = "world-cup-winner") -> list[ChampionQuote]:
    settings = get_settings()
    params = urlencode({"slug": event_slug})
    url = f"{settings.polymarket_gamma_api_base.rstrip('/')}/events?{params}"
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "world-cup-forecast/0.1"})
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Polymarket WC winner fetch failed for {event_slug}: {exc}") from exc
    if not payload:
        return []
    event = payload[0]
    quotes: list[ChampionQuote] = []
    for market in event.get("markets", []):
        quote = _parse_market(market, event_slug=event_slug)
        if quote is not None:
            quotes.append(quote)
    return quotes


def _parse_market(row: dict[str, Any], *, event_slug: str) -> ChampionQuote | None:
    question = row.get("question") or row.get("title") or ""
    team_label = parse_polymarket_team_label(question)
    if team_label is None:
        return None
    yes_price = _yes_price(row)
    if yes_price is None:
        return None
    return ChampionQuote(
        platform="polymarket",
        team_label=team_label,
        yes_price=yes_price,
        external_id=str(row.get("id") or row.get("conditionId") or question),
    )


def _yes_price(row: dict[str, Any]) -> float | None:
    prices = row.get("outcomePrices")
    if isinstance(prices, str):
        try:
            prices = json.loads(prices)
        except json.JSONDecodeError:
            prices = None
    if isinstance(prices, list) and prices:
        try:
            return float(prices[0])
        except (TypeError, ValueError):
            return None
    best_bid = _to_float(row.get("bestBid"))
    best_ask = _to_float(row.get("bestAsk"))
    if best_bid is not None and best_ask is not None:
        return (best_bid + best_ask) / 2
    last = _to_float(row.get("lastTradePrice"))
    if last is not None:
        return last
    return None


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)
