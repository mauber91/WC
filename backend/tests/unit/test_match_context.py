from datetime import datetime, timezone

from world_cup_api.domain.match_context import group_match_context, rest_days_between


def test_rest_days_between_matches() -> None:
    first = datetime(2026, 6, 11, 19, tzinfo=timezone.utc)
    second = datetime(2026, 6, 18, 16, tzinfo=timezone.utc)
    assert rest_days_between(first, second) == 6.875


def test_group_match_context_uses_base_camp_travel() -> None:
    t1, t2 = 1, 2
    scheduled = datetime(2026, 6, 11, 19, tzinfo=timezone.utc)
    matches = [{"id": 10, "a": t1, "b": t2, "scheduled_at": scheduled, "venue": "Estadio Azteca"}]
    ctx = group_match_context(matches, {t1: "MEX", t2: "RSA"})
    assert ctx[10]["travel_a"] < 30
    assert ctx[10]["rest_a"] == 0.0


def test_group_matchday_two_increments_rest() -> None:
    t1, t2, t3, t4 = 1, 2, 3, 4
    md1 = datetime(2026, 6, 11, 19, tzinfo=timezone.utc)
    md1b = datetime(2026, 6, 11, 22, tzinfo=timezone.utc)
    md2 = datetime(2026, 6, 18, 16, tzinfo=timezone.utc)
    md2b = datetime(2026, 6, 18, 19, tzinfo=timezone.utc)
    matches = [
        {"id": 1, "a": t1, "b": t2, "scheduled_at": md1, "venue": "Estadio Azteca"},
        {"id": 2, "a": t3, "b": t4, "scheduled_at": md1b, "venue": "Estadio Akron"},
        {"id": 3, "a": t1, "b": t3, "scheduled_at": md2, "venue": "Mercedes-Benz Stadium"},
        {"id": 4, "a": t2, "b": t4, "scheduled_at": md2b, "venue": "Estadio BBVA"},
    ]
    ctx = group_match_context(matches, {t1: "MEX", t2: "RSA", t3: "KOR", t4: "CZE"})
    assert ctx[3]["rest_a"] > 6.0
    assert ctx[3]["travel_a"] > 1000
