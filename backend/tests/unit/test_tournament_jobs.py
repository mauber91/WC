from __future__ import annotations

from unittest.mock import patch

from world_cup_api.jobs.tournament_jobs import run_market_sync_job, run_seed_refresh_job, start_tournament_jobs
from world_cup_api.services.tournament_refresh import TournamentRefreshReport


def test_seed_refresh_job_skips_when_disabled(monkeypatch) -> None:
    monkeypatch.setenv("WC_SEED_REFRESH_ENABLED", "false")
    from world_cup_api.config import get_settings

    get_settings.cache_clear()
    with patch("world_cup_api.jobs.tournament_jobs.refresh_tournament_data") as refresh:
        run_seed_refresh_job()
    refresh.assert_not_called()
    get_settings.cache_clear()


def test_start_tournament_jobs_registers_refresh_and_market_sync(monkeypatch) -> None:
    monkeypatch.setenv("WC_ENABLE_SCHEDULER", "true")
    monkeypatch.setenv("WC_SEED_REFRESH_ENABLED", "true")
    monkeypatch.setenv("WC_MARKET_SYNC_ENABLED", "true")
    monkeypatch.setenv("WC_SEED_REFRESH_ON_STARTUP", "false")
    monkeypatch.setenv("WC_MARKET_SYNC_ON_STARTUP", "false")
    from world_cup_api.config import get_settings
    from world_cup_api.jobs.scheduler import scheduler

    get_settings.cache_clear()
    scheduler.remove_all_jobs()
    start_tournament_jobs(run_immediately=True)
    job_ids = {job.id for job in scheduler.get_jobs()}
    assert "seed-refresh-daily" in job_ids
    assert "market-sync-interval" in job_ids
    assert "seed-refresh-startup" not in job_ids
    assert "market-sync-startup" not in job_ids
    scheduler.shutdown(wait=False)
    get_settings.cache_clear()


def test_start_tournament_jobs_schedules_immediate_startup_jobs(monkeypatch) -> None:
    monkeypatch.setenv("WC_ENABLE_SCHEDULER", "true")
    monkeypatch.setenv("WC_SEED_REFRESH_ENABLED", "true")
    monkeypatch.setenv("WC_MARKET_SYNC_ENABLED", "true")
    monkeypatch.setenv("WC_SEED_REFRESH_ON_STARTUP", "true")
    monkeypatch.setenv("WC_MARKET_SYNC_ON_STARTUP", "true")
    from world_cup_api.config import get_settings
    from world_cup_api.jobs.scheduler import scheduler

    get_settings.cache_clear()
    scheduler.remove_all_jobs()
    start_tournament_jobs(run_immediately=True)
    job_ids = {job.id for job in scheduler.get_jobs()}
    assert "seed-refresh-startup" in job_ids
    assert "market-sync-startup" in job_ids
    scheduler.shutdown(wait=False)
    get_settings.cache_clear()


def test_seed_refresh_job_runs_refresh(monkeypatch) -> None:
    monkeypatch.setenv("WC_SEED_REFRESH_ENABLED", "true")
    from world_cup_api.config import get_settings

    get_settings.cache_clear()
    report = TournamentRefreshReport(fetched=1, applied=1, skipped=0, warnings=(), seed_regenerated=False)
    with patch("world_cup_api.jobs.tournament_jobs.refresh_tournament_data", return_value=report) as refresh:
        run_seed_refresh_job()
    refresh.assert_called_once()
    get_settings.cache_clear()


def test_market_sync_job_skips_when_disabled(monkeypatch) -> None:
    monkeypatch.setenv("WC_MARKET_SYNC_ENABLED", "false")
    from world_cup_api.config import get_settings

    get_settings.cache_clear()
    with patch("world_cup_api.jobs.tournament_jobs.sync_upcoming_markets") as sync:
        run_market_sync_job()
    sync.assert_not_called()
    get_settings.cache_clear()
