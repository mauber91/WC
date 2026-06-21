from __future__ import annotations

from world_cup_api.services.squad_sync import SEASON_SPECS_BY_LABEL, season_extraction_status


def test_season_specs_cover_requested_labels() -> None:
    assert set(SEASON_SPECS_BY_LABEL) == {"25-26", "24-25", "23-24"}


def test_season_extraction_status_shape() -> None:
    statuses = season_extraction_status()
    assert len(statuses) == 3
    assert all(status.teams_expected > 0 for status in statuses)
