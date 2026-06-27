from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from world_cup_api.config import get_settings
from world_cup_api.ingestion.quote_prices import reliable_yes_price


@dataclass(frozen=True)
class KalshiEvent:
    event_ticker: str
    title: str


KXWCGAME_SERIES = "KXWCGAME"


@dataclass(frozen=True)
class KalshiMarketQuote:
    event_ticker: str
    ticker: str
    title: str
    outcome_label: str
    yes_price: float
    best_bid: float | None
    best_ask: float | None
    volume: float | None


def fetch_series_events(series_ticker: str, *, limit: int = 200) -> list[KalshiEvent]:
    settings = get_settings()
    params = urlencode({"series_ticker": series_ticker, "limit": limit})
    url = f"{settings.kalshi_api_base.rstrip('/')}/events?{params}"
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "world-cup-forecast/0.1"})
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Kalshi event fetch failed for {series_ticker}: {exc}") from exc
    return [
        KalshiEvent(event_ticker=row["event_ticker"], title=row.get("title") or "")
        for row in payload.get("events", [])
    ]


def fetch_event_markets(event_ticker: str, *, limit: int = 100) -> list[KalshiMarketQuote]:
    settings = get_settings()
    params = urlencode({"event_ticker": event_ticker, "limit": limit})
    url = f"{settings.kalshi_api_base.rstrip('/')}/markets?{params}"
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "world-cup-forecast/0.1"})
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Kalshi market fetch failed for {event_ticker}: {exc}") from exc
    quotes: list[KalshiMarketQuote] = []
    for row in payload.get("markets", []):
        quote = _parse_market(row)
        if quote is not None:
            quotes.append(quote)
    return quotes


def _parse_market(row: dict[str, Any]) -> KalshiMarketQuote | None:
    yes_bid = _to_float(row.get("yes_bid_dollars"))
    yes_ask = _to_float(row.get("yes_ask_dollars"))
    last = _to_float(row.get("last_price_dollars"))
    yes_price = reliable_yes_price(yes_bid=yes_bid, yes_ask=yes_ask, last=last)
    if yes_price is None:
        return None
    return KalshiMarketQuote(
        event_ticker=row["event_ticker"],
        ticker=row["ticker"],
        title=row["title"],
        outcome_label=row.get("yes_sub_title") or row.get("subtitle") or row["title"],
        yes_price=yes_price,
        best_bid=yes_bid,
        best_ask=yes_ask,
        volume=_to_float(row.get("volume_fp")),
    )


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)
