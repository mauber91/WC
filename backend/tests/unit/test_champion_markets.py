from world_cup_api.domain.champion_markets import (
    build_fifa_label_index,
    champion_probability_to_elo,
    match_champion_label,
    normalize_champion_probabilities,
    parse_polymarket_team_label,
    pool_champion_probability,
)
from world_cup_api.domain.team_strength import fuse_strength
from world_cup_api.modeling.context_params import DEFAULT_CONTEXT_PARAMS


class _Team:
    def __init__(self, fifa_code: str, name: str) -> None:
        self.fifa_code = fifa_code
        self.name = name


def test_parse_polymarket_team_label() -> None:
    assert parse_polymarket_team_label("Will France win the 2026 FIFA World Cup?") == "France"
    assert parse_polymarket_team_label("Will Team AM win the 2026 FIFA World Cup?") == "Team AM"


def test_match_champion_label_handles_aliases() -> None:
    teams = [
        _Team("CIV", "Côte d'Ivoire"),
        _Team("TUR", "Türkiye"),
        _Team("KOR", "Korea Republic"),
        _Team("CUW", "Curaçao"),
    ]
    index = build_fifa_label_index(teams)
    assert match_champion_label("Ivory Coast", index) == "CIV"
    assert match_champion_label("Turkey", index) == "TUR"
    assert match_champion_label("South Korea", index) == "KOR"
    assert match_champion_label("Curacao", index) == "CUW"


def test_pool_champion_probability_geometric_mean() -> None:
    pooled = pool_champion_probability([0.20, 0.18])
    assert pooled is not None
    assert 0.18 < pooled < 0.20


def test_champion_probability_to_elo_favors_favorites() -> None:
    favorite = champion_probability_to_elo(0.20, field_size=48)
    longshot = champion_probability_to_elo(0.001, field_size=48)
    assert favorite > longshot


def test_fuse_strength_boosts_france_over_jordan() -> None:
    params = DEFAULT_CONTEXT_PARAMS
    france = fuse_strength(
        1850,
        10,
        fifa_weight=params.fifa_strength_weight,
        champion_prob=0.20,
        champion_weight=params.champion_strength_weight,
        champion_field_size=48,
    )
    jordan = fuse_strength(
        1650,
        70,
        fifa_weight=params.fifa_strength_weight,
        champion_prob=0.001,
        champion_weight=params.champion_strength_weight,
        champion_field_size=48,
    )
    assert france > jordan


def test_normalize_champion_probabilities_sums_to_one() -> None:
    normalized = normalize_champion_probabilities({"FRA": 0.20, "ESP": 0.14, "BRA": 0.06})
    assert abs(sum(normalized.values()) - 1.0) < 1e-9
