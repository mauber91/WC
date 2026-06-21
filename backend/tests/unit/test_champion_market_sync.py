from unittest.mock import patch

from sqlalchemy import select

from world_cup_api.db.models import Team, TeamRating
from world_cup_api.domain.champion_markets import ChampionQuote, WC_CHAMPION_RATING_TYPE
from world_cup_api.ingestion.kalshi import KalshiMarketQuote
from world_cup_api.services.champion_market_sync import sync_wc_champion_markets
from world_cup_api.services.seed import seed_database


def test_sync_wc_champion_markets_stores_consensus(db_session) -> None:
    seed_database(db_session)
    poly_quotes = [
        ChampionQuote(platform="polymarket", team_label="France", yes_price=0.198, external_id="p1"),
        ChampionQuote(platform="polymarket", team_label="Spain", yes_price=0.137, external_id="p2"),
    ]
    kalshi_quotes = [
        KalshiMarketQuote(
            event_ticker="KXMENWORLDCUP-26",
            ticker="KXMENWORLDCUP-26-FR",
            title="France WC winner",
            outcome_label="France",
            yes_price=0.193,
            best_bid=0.193,
            best_ask=0.194,
            volume=1000.0,
        ),
    ]
    with patch("world_cup_api.services.champion_market_sync.fetch_wc_winner_quotes", return_value=poly_quotes), \
         patch("world_cup_api.services.champion_market_sync.fetch_event_markets", return_value=kalshi_quotes):
        report = sync_wc_champion_markets(db_session)

    assert report.teams_matched >= 2
    assert report.stored_rows > 0
    assert "polymarket" in report.platforms
    assert "kalshi" in report.platforms
    assert any(code == "FRA" for code, _ in report.top_favorites)

    france = db_session.scalar(select(Team).where(Team.fifa_code == "FRA"))
    assert france is not None
    rating = db_session.scalar(
        select(TeamRating)
        .where(
            TeamRating.team_id == france.id,
            TeamRating.rating_type == WC_CHAMPION_RATING_TYPE,
            TeamRating.source == "consensus",
        )
        .order_by(TeamRating.effective_at.desc())
    )
    assert rating is not None
    assert report.top_favorites[0][0] == "FRA"
    assert rating.rating_value == report.top_favorites[0][1]
