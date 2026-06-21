from world_cup_api.domain.venues import GeoPoint, haversine_km, team_base_camps, travel_km_from_base, venue_catalog


def test_venue_catalog_loads_stadiums() -> None:
    venues = venue_catalog()
    assert "Estadio Azteca" in venues
    assert venues["Estadio Azteca"].country == "MX"


def test_team_base_camps_cover_all_draw_teams() -> None:
    camps = team_base_camps()
    assert camps["MEX"].lat == 19.4326
    assert camps["USA"].lat == 33.6846
    assert camps["KOR"].lon == -103.3496
    assert len(camps) == 48


def test_haversine_km_is_symmetric() -> None:
    la = GeoPoint(34.0522, -118.2437)
    seattle = GeoPoint(47.6062, -122.3321)
    assert haversine_km(la, seattle) == haversine_km(seattle, la)


def test_mexico_travels_from_base_camp_to_azteca() -> None:
    km = travel_km_from_base("MEX", "Estadio Azteca")
    assert 0 <= km < 30
