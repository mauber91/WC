from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from sqlalchemy import select

from world_cup_api.db.models import Match, MatchResult, Team, Tournament
from world_cup_api.ingestion.fifa import FifaGroupResult
from world_cup_api.services.tournament_refresh import refresh_tournament_data


def test_refresh_applies_new_fifa_result(db_session, monkeypatch) -> None:
    monkeypatch.setenv("WC_SEED_REGENERATE_CSVS", "false")
    from world_cup_api.config import get_settings

    get_settings.cache_clear()
    tournament = Tournament(code="FWC2026", name="Test", year=2026, starts_on=datetime(2026, 6, 11).date(),
                            ends_on=datetime(2026, 7, 19).date(), ruleset_version="test")
    team_a = Team(fifa_code="GER", name="Germany", short_name="Germany", country_code="DE", confederation="UEFA")
    team_b = Team(fifa_code="CIV", name="Côte d'Ivoire", short_name="Côte d'Ivoire", country_code="CI", confederation="CAF")
    db_session.add_all([tournament, team_a, team_b])
    db_session.flush()
    match = Match(
        tournament_id=tournament.id,
        official_match_number=33,
        stage="group",
        team_a_id=team_a.id,
        team_b_id=team_b.id,
        scheduled_at=datetime(2026, 6, 20, 20, 0, tzinfo=timezone.utc),
        status="scheduled",
    )
    db_session.add(match)
    db_session.commit()

    live = [FifaGroupResult(33, "GER", "CIV", 0, 1, 0)]
    with patch("world_cup_api.services.tournament_refresh.fetch_finished_group_results", return_value=live):
        report = refresh_tournament_data(db_session, regenerate_seed_files=False)

    assert report.applied == 1
    result = db_session.scalar(select(MatchResult).where(MatchResult.match_id == match.id, MatchResult.is_current.is_(True)))
    assert result is not None
    assert result.team_a_goals_90 == 0
    assert result.team_b_goals_90 == 1
    db_session.refresh(match)
    assert match.status == "final"
    get_settings.cache_clear()


def test_refresh_skips_unchanged_result(db_session, monkeypatch) -> None:
    monkeypatch.setenv("WC_SEED_REGENERATE_CSVS", "false")
    from world_cup_api.config import get_settings

    get_settings.cache_clear()
    tournament = Tournament(code="FWC2026", name="Test", year=2026, starts_on=datetime(2026, 6, 11).date(),
                            ends_on=datetime(2026, 7, 19).date(), ruleset_version="test")
    team_a = Team(fifa_code="GER", name="Germany", short_name="Germany", country_code="DE", confederation="UEFA")
    team_b = Team(fifa_code="CIV", name="Côte d'Ivoire", short_name="Côte d'Ivoire", country_code="CI", confederation="CAF")
    db_session.add_all([tournament, team_a, team_b])
    db_session.flush()
    match = Match(
        tournament_id=tournament.id,
        official_match_number=33,
        stage="group",
        team_a_id=team_a.id,
        team_b_id=team_b.id,
        scheduled_at=datetime(2026, 6, 20, 20, 0, tzinfo=timezone.utc),
        status="final",
    )
    db_session.add(match)
    db_session.flush()
    db_session.add(MatchResult(
        match_id=match.id,
        revision=1,
        is_current=True,
        team_a_goals_90=0,
        team_b_goals_90=1,
        recorded_at=datetime.now(timezone.utc),
        source_updated_at=datetime.now(timezone.utc),
        source="seed",
    ))
    db_session.commit()

    live = [FifaGroupResult(33, "GER", "CIV", 0, 1, 0)]
    with patch("world_cup_api.services.tournament_refresh.fetch_finished_group_results", return_value=live):
        report = refresh_tournament_data(db_session, regenerate_seed_files=False)

    assert report.applied == 0
    assert report.skipped == 1
    revisions = db_session.scalars(select(MatchResult).where(MatchResult.match_id == match.id)).all()
    assert len(revisions) == 1
    get_settings.cache_clear()
