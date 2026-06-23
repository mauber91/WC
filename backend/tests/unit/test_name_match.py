from world_cup_api.domain.name_match import names_match


def test_names_match_handles_accents_and_order() -> None:
    assert names_match("Jude Bellingham", "Bellingham, Jude")
    assert names_match("Kylian Mbappé", "Kylian Mbappe")


def test_names_match_rejects_unrelated_players() -> None:
    assert not names_match("Harry Kane", "Lionel Messi")
