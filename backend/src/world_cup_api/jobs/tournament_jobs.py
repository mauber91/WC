from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.jobstores.base import JobLookupError

from world_cup_api.config import get_settings
from world_cup_api.db.session import SessionLocal
from world_cup_api.jobs.scheduler import scheduler, shutdown_scheduler
from world_cup_api.services.champion_market_sync import sync_wc_champion_markets
from world_cup_api.services.market_sync import sync_upcoming_markets
from world_cup_api.services.tournament_refresh import refresh_tournament_data

logger = logging.getLogger(__name__)


def run_seed_refresh_job() -> None:
    settings = get_settings()
    if not settings.seed_refresh_enabled:
        return
    logger.info("Running tournament seed refresh")
    with SessionLocal() as db:
        try:
            report = refresh_tournament_data(db, regenerate_seed_files=settings.seed_regenerate_csvs)
        except Exception:
            logger.exception("Scheduled seed refresh failed")
            return
    if report.applied:
        logger.info(
            "Seed refresh applied %s results (%s fetched, seed files regenerated=%s)",
            report.applied,
            report.fetched,
            report.seed_regenerated,
        )
    elif report.warnings:
        logger.warning("Seed refresh completed with warnings: %s", "; ".join(report.warnings))
    else:
        logger.info("Seed refresh found no new finished matches (%s already current)", report.fetched)


def run_market_sync_job() -> None:
    settings = get_settings()
    if not settings.market_sync_enabled:
        return
    logger.info("Running prediction market sync")
    with SessionLocal() as db:
        try:
            reports = sync_upcoming_markets(db)
            champion_report = sync_wc_champion_markets(db)
        except Exception:
            logger.exception("Scheduled market sync failed")
            return
    stored = sum(report.stored_rows for report in reports)
    if stored:
        platforms = sorted({platform for report in reports for platform in report.platforms})
        logger.info("Market sync stored %s rows across %s fixtures (%s)", stored, len(reports), ", ".join(platforms))
    else:
        logger.info("Market sync completed with no new rows for %s fixtures", len(reports))
    if champion_report.stored_rows:
        logger.info(
            "WC champion market sync stored %s rows for %s teams (%s)",
            champion_report.stored_rows,
            champion_report.teams_matched,
            ", ".join(champion_report.platforms),
        )
    elif champion_report.warnings:
        logger.warning("WC champion market sync warnings: %s", "; ".join(champion_report.warnings))


def _schedule_immediate(job_id: str, func, *, delay_seconds: int = 0) -> None:
    scheduler.add_job(
        func,
        trigger="date",
        run_date=datetime.now(timezone.utc) + timedelta(seconds=delay_seconds),
        id=job_id,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )


def stop_tournament_jobs() -> None:
    for job_id in (
        "seed-refresh-daily",
        "seed-refresh-startup",
        "market-sync-interval",
        "market-sync-startup",
    ):
        try:
            scheduler.remove_job(job_id)
        except JobLookupError:
            pass
    shutdown_scheduler()


def start_tournament_jobs(*, run_immediately: bool = False) -> None:
    settings = get_settings()
    if not settings.enable_scheduler:
        return
    if not scheduler.running:
        scheduler.start()

    if settings.seed_refresh_enabled:
        scheduler.add_job(
            run_seed_refresh_job,
            trigger="cron",
            hour=settings.seed_refresh_hour_utc,
            minute=settings.seed_refresh_minute_utc,
            id="seed-refresh-daily",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        if run_immediately and settings.seed_refresh_on_startup:
            _schedule_immediate("seed-refresh-startup", run_seed_refresh_job, delay_seconds=2)

    if settings.market_sync_enabled:
        scheduler.add_job(
            run_market_sync_job,
            trigger="interval",
            minutes=settings.market_sync_interval_minutes,
            id="market-sync-interval",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        if run_immediately and settings.market_sync_on_startup:
            _schedule_immediate("market-sync-startup", run_market_sync_job, delay_seconds=15)
