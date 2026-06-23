from world_cup_api.domain.host_advantage import venue_home_flags


def test_mexico_gets_boost_in_mexico_city_not_los_angeles() -> None:
    assert venue_home_flags("MX", "GB", "MX") == (True, False)
    assert venue_home_flags("MX", "GB", "US") == (False, False)


def test_usa_and_canada_only_boost_in_own_country() -> None:
    assert venue_home_flags("US", "GB", "US") == (True, False)
    assert venue_home_flags("CA", "BR", "CA") == (True, False)
    assert venue_home_flags("US", "CA", "CA") == (False, True)


def test_non_co_host_never_gets_venue_boost() -> None:
    assert venue_home_flags("GB", "AR", "US") == (False, False)


def test_unknown_host_country_disables_boost() -> None:
    assert venue_home_flags("MX", "GB", "") == (False, False)
