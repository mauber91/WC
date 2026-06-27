from world_cup_api.ingestion.quote_prices import reliable_yes_price


def test_reliable_yes_price_uses_tight_spread_midpoint() -> None:
    assert reliable_yes_price(yes_bid=0.225, yes_ask=0.230, last=0.230) == 0.2275


def test_reliable_yes_price_ignores_wide_spread_midpoint() -> None:
    # Haiti-style book: 0 / 1 with last trade at 0.001
    assert reliable_yes_price(yes_bid=0.0, yes_ask=1.0, last=0.001) == 0.001


def test_reliable_yes_price_skips_placeholder_book() -> None:
    assert reliable_yes_price(yes_bid=0.0, yes_ask=1.0, last=0.0) is None
