from world_cup_api.services.power_rankings import blend_power_score, tournament_power_score


def test_tournament_power_score_weights_champion_most() -> None:
    favorite = tournament_power_score({
        "champion": 0.20,
        "final": 0.30,
        "semifinal": 0.40,
        "quarterfinal": 0.50,
        "round_of_16": 0.60,
        "round_of_32": 0.70,
    })
    long_shot = tournament_power_score({
        "champion": 0.01,
        "final": 0.02,
        "semifinal": 0.03,
        "quarterfinal": 0.05,
        "round_of_16": 0.10,
        "round_of_32": 0.15,
    })
    assert favorite > long_shot


def test_tournament_power_score_is_monotonic_with_champion_prob() -> None:
    base = {"final": 0.1, "semifinal": 0.2, "quarterfinal": 0.3, "round_of_16": 0.4, "round_of_32": 0.5}
    low = tournament_power_score({**base, "champion": 0.05})
    high = tournament_power_score({**base, "champion": 0.15})
    assert high > low


def test_blend_power_score_favors_market_leader() -> None:
    probs = {
        "champion": 0.12,
        "final": 0.18,
        "semifinal": 0.25,
        "quarterfinal": 0.35,
        "round_of_16": 0.45,
        "round_of_32": 0.55,
    }
    sim_only = blend_power_score(probs, 0.20, market_blend=0.0, max_market_prob=0.20)
    blended = blend_power_score(probs, 0.20, market_blend=0.30, max_market_prob=0.20)
    underdog = blend_power_score(probs, 0.10, market_blend=0.30, max_market_prob=0.20)
    assert sim_only == tournament_power_score(probs)
    assert blended > underdog
