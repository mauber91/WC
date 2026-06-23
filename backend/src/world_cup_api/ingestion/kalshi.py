from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from world_cup_api.config import get_settings


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
        quotes.append(_parse_market(row))
    return quotes


def _parse_market(row: dict[str, Any]) -> KalshiMarketQuote:
    yes_bid = _to_float(row.get("yes_bid_dollars"))
    yes_ask = _to_float(row.get("yes_ask_dollars"))
    last = _to_float(row.get("last_price_dollars"))
    yes_price = ((yes_bid + yes_ask) / 2) if yes_bid is not None and yes_ask is not None else last
    if yes_price is None:
        yes_price = 0.0
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
