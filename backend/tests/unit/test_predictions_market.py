from world_cup_api.db.models import BookmakerOdds, Match
from world_cup_api.services.predictions import _market_consensus
from world_cup_api.services.seed import seed_database


def test_market_consensus_ignores_model_consensus(db_session) -> None:
    seed_database(db_session)
    match = db_session.query(Match).filter(Match.official_match_number == 52).one()
    db_session.add(BookmakerOdds(
        match_id=match.id,
        bookmaker="888sport",
        market_type="1X2",
        selection="team_a",
        decimal_odds=2.1,
        snapshot_at=match.scheduled_at,
    ))
    db_session.add(BookmakerOdds(
        match_id=match.id,
        bookmaker="888sport",
        market_type="1X2",
        selection="draw",
        decimal_odds=3.4,
        snapshot_at=match.scheduled_at,
    ))
    db_session.add(BookmakerOdds(
        match_id=match.id,
        bookmaker="888sport",
        market_type="1X2",
        selection="team_b",
        decimal_odds=3.6,
        snapshot_at=match.scheduled_at,
    ))
    db_session.commit()

    market, sources, has_external = _market_consensus(db_session, match.id)
    assert has_external
    assert market is not None
    assert any(source.get("bookmaker") == "888sport" for source in sources)
    assert all(source.get("bookmaker") != "model-consensus" for source in sources if "bookmaker" in source)
