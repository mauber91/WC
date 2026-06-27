from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from sqlalchemy import select

from world_cup_api.db.models import Match, PredictionMarketPrice, Team, Tournament
from world_cup_api.ingestion.attena import AttenaMarketResult
from world_cup_api.ingestion.kalshi import KalshiEvent, KalshiMarketQuote
from world_cup_api.services.market_sync import (
    _event_title_matches_teams,
    _find_kxwcgame_event_ticker,
    _map_selection,
    sync_upcoming_markets,
)


def test_map_selection_handles_kalshi_labels() -> None:
    team_a = Team(fifa_code="GER", name="Germany", short_name="Germany")
    team_b = Team(fifa_code="CIV", name="Côte d'Ivoire", short_name="Côte d'Ivoire")
    assert _map_selection("Germany", team_a, team_b) == "team_a"
    assert _map_selection("Ivory Coast", team_a, team_b) == "team_b"
    assert _map_selection("Tie", team_a, team_b) == "draw"


def test_sync_match_stores_kalshi_quotes_from_attena_and_enrichment(db_session) -> None:
    tournament = Tournament(code="FWC2026", name="Test", year=2026, starts_on=datetime(2026, 6, 11).date(),
                            ends_on=datetime(2026, 7, 19).date(), ruleset_version="test")
    team_a = Team(fifa_code="GER", name="Germany", short_name="Germany", country_code="DE", confederation="UEFA")
    team_b = Team(fifa_code="CIV", name="Côte d'Ivoire", short_name="Côte d'Ivoire", country_code="CI", confederation="CAF")
    db_session.add_all([tournament, team_a, team_b])
    db_session.flush()
    match = Match(
        tournament_id=tournament.id,
        official_match_number=33,
        stage="group",
        team_a_id=team_a.id,
        team_b_id=team_b.id,
        scheduled_at=datetime(2026, 6, 20, 20, 0, tzinfo=timezone.utc),
        status="scheduled",
    )
    db_session.add(match)
    db_session.commit()

    attena_rows = [
        AttenaMarketResult(
            title="FIFA World Cup: Germany vs Ivory Coast",
            category="sports",
            subcategory="world_cup",
            league="FIFA World Cup",
            event_date="2026-06-20",
            source="kalshi",
            market_id="KXWCGAME-26JUN20GERCIV-GER",
            yes_price=0.11,
            no_price=0.41,
            volume=1000.0,
            volume_24h=500.0,
            source_url="https://kalshi.com/markets/kxwcgame/kxwcgame-26jun20gerciv",
            outcome_label="Germany",
            bracket_count=3,
            rank=0.4,
        ),
    ]
    kalshi_rows = [
        KalshiMarketQuote("KXWCGAME-26JUN20GERCIV", "KXWCGAME-26JUN20GERCIV-GER", "Germany vs Ivory Coast Winner?",
                          "Germany", 0.41, 0.40, 0.42, 1000.0),
        KalshiMarketQuote("KXWCGAME-26JUN20GERCIV", "KXWCGAME-26JUN20GERCIV-TIE", "Germany vs Ivory Coast Winner?",
                          "Tie", 0.30, 0.29, 0.31, 800.0),
        KalshiMarketQuote("KXWCGAME-26JUN20GERCIV", "KXWCGAME-26JUN20GERCIV-CIV", "Germany vs Ivory Coast Winner?",
                          "Ivory Coast", 0.41, 0.40, 0.42, 900.0),
    ]

    with patch("world_cup_api.services.market_sync.search_markets", return_value=attena_rows), \
         patch("world_cup_api.services.market_sync.fetch_event_markets", return_value=kalshi_rows), \
         patch("world_cup_api.services.market_sync.fetch_series_events", return_value=[]):
        reports = sync_upcoming_markets(db_session, match_numbers=[33])

    assert len(reports) == 1
    assert reports[0].stored_rows == 3
    rows = db_session.scalars(
        select(PredictionMarketPrice).where(PredictionMarketPrice.match_id == match.id)
    ).all()
    assert len(rows) == 3
    assert {row.platform for row in rows} == {"kalshi"}
    assert abs(sum(row.yes_price for row in rows) - 1.0) < 1e-6


def test_find_kxwcgame_event_ticker_matches_team_names() -> None:
    team_a = Team(fifa_code="ALG", name="Algeria", short_name="Algeria")
    team_b = Team(fifa_code="AUT", name="Austria", short_name="Austria")
    events = [KalshiEvent("KXWCGAME-26JUN27DZAAUT", "Algeria vs Austria")]
    assert _find_kxwcgame_event_ticker(team_a, team_b, events) == "KXWCGAME-26JUN27DZAAUT"
    assert _event_title_matches_teams("Panama vs England: Regulation Time Moneyline",
                                      Team(fifa_code="PAN", name="Panama", short_name="Panama"),
                                      Team(fifa_code="ENG", name="England", short_name="England"))
