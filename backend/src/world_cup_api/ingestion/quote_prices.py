from __future__ import annotations

# Wide bid/ask spreads (e.g. 0 / 1 on illiquid Kalshi/Polymarket contracts) must not
# be mid-pointed to 0.50 — that inverts outright-winner rankings.
MAX_BID_ASK_SPREAD = 0.20


def reliable_yes_price(
    *,
    yes_bid: float | None,
    yes_ask: float | None,
    last: float | None,
    max_spread: float = MAX_BID_ASK_SPREAD,
) -> float | None:
    if yes_bid is not None and yes_ask is not None:
        spread = yes_ask - yes_bid
        if spread <= max_spread and yes_bid > 0 and yes_ask < 1:
            return (yes_bid + yes_ask) / 2
    if last is not None and last > 0:
        return last
    return None
