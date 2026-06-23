from world_cup_api.domain.team_strength import SYNTHETIC_BOOKMAKERS, fuse_strength, fifa_rank_to_elo
from world_cup_api.modeling.context_params import DEFAULT_CONTEXT_PARAMS


def test_fifa_rank_to_elo_decreases_with_rank() -> None:
    assert fifa_rank_to_elo(1) > fifa_rank_to_elo(64)


def test_fuse_strength_keeps_bosnia_above_qatar() -> None:
    w = DEFAULT_CONTEXT_PARAMS.fifa_strength_weight
    bih = fuse_strength(1596, 64, fifa_weight=w)
    qat = fuse_strength(1437, 56, fifa_weight=w)
    assert bih > qat


def test_model_consensus_is_synthetic() -> None:
    assert "model-consensus" in SYNTHETIC_BOOKMAKERS
