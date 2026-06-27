from world_cup_api.services.power_rankings import tournament_power_score


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
