from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from world_cup_api.config import get_settings


@dataclass(frozen=True)
class AttenaMarketResult:
    title: str
    category: str | None
    subcategory: str | None
    league: str | None
    event_date: str | None
    source: str
    market_id: str
    yes_price: float
    no_price: float | None
    volume: float | None
    volume_24h: float | None
    source_url: str | None
    outcome_label: str | None
    bracket_count: int | None
    rank: float | None


def search_markets(query: str, *, limit: int = 30) -> list[AttenaMarketResult]:
    settings = get_settings()
    params = urlencode({"q": query, "limit": limit})
    url = f"{settings.attena_api_base.rstrip('/')}/?{params}"
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "world-cup-forecast/0.1"})
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Attena search failed for {query!r}: {exc}") from exc
    return [_parse_result(row) for row in payload.get("results", [])]


def _parse_result(row: dict[str, Any]) -> AttenaMarketResult:
    return AttenaMarketResult(
        title=row["title"],
        category=row.get("category"),
        subcategory=row.get("subcategory"),
        league=row.get("league"),
        event_date=row.get("event_date"),
        source=row["source"],
        market_id=row["market_id"],
        yes_price=float(row["yes_price"]),
        no_price=float(row["no_price"]) if row.get("no_price") is not None else None,
        volume=float(row["volume"]) if row.get("volume") is not None else None,
        volume_24h=float(row["volume_24h"]) if row.get("volume_24h") is not None else None,
        source_url=row.get("source_url"),
        outcome_label=row.get("outcome_label"),
        bracket_count=int(row["bracket_count"]) if row.get("bracket_count") is not None else None,
        rank=float(row["rank"]) if row.get("rank") is not None else None,
    )
