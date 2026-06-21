from world_cup_api.domain.teams import team_ref_matches, team_slug


def test_team_slug_from_name() -> None:
    assert team_slug("Mexico") == "mexico"
    assert team_slug("Korea Republic") == "korea-republic"
    assert team_slug("United States") == "united-states"


def test_team_ref_matches_slug_or_code() -> None:
    assert team_ref_matches("Mexico", "MEX", "mexico")
    assert team_ref_matches("Mexico", "MEX", "MEX")
    assert not team_ref_matches("Mexico", "MEX", "spain")
