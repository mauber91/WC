from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from world_cup_api.config import get_settings


def test_alembic_upgrade_creates_report_schema(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "migration.db"
    monkeypatch.setenv("WC_DATABASE_URL", f"sqlite:///{database}")
    get_settings.cache_clear()
    try:
        backend_root = Path(__file__).resolve().parents[2]
        config = Config(backend_root / "alembic.ini")
        command.upgrade(config, "head")
        tables = set(inspect(create_engine(f"sqlite:///{database}")).get_table_names())
        assert {
            "match_report_documents",
            "match_report_extraction_runs",
            "match_report_pages",
            "match_report_page_payloads",
            "match_report_participants",
            "match_report_metric_definitions",
            "match_report_observations",
            "match_report_events",
            "match_report_spatial_features",
            "match_report_network_edges",
            "match_report_timeseries_points",
            "match_report_issues",
        } <= tables
    finally:
        get_settings.cache_clear()
