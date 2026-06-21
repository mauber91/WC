from __future__ import annotations

import shutil
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from world_cup_api.config import ROOT_DIR
from world_cup_api.db.report_models import MatchReportDocument, MatchReportExtractionRun
from world_cup_api.pipelines.fifa_pmsr.constants import PIPELINE_VERSION
from world_cup_api.pipelines.fifa_pmsr.extract import extract_report
from world_cup_api.pipelines.fifa_pmsr.inspect import inspect_report
from world_cup_api.pipelines.fifa_pmsr.loader import load_extraction
from world_cup_api.pipelines.fifa_pmsr.types import IngestionSummary


def _summary_from_run(document: MatchReportDocument, run: MatchReportExtractionRun) -> IngestionSummary:
    counts = {key: int(value) for key, value in run.stats_json.items() if isinstance(value, int)}
    return IngestionSummary(
        document_id=document.id,
        extraction_run_id=run.id,
        sha256=document.sha256,
        status=run.status,
        reused=True,
        artifact_root=run.artifact_root,
        page_count=document.page_count,
        quality_score=run.quality_score or 0,
        coverage=run.coverage or 0,
        counts=counts,
    )


def ingest_report(
    session: Session,
    path: str | Path,
    force: bool = False,
    dry_run: bool = False,
) -> IngestionSummary:
    manifest = inspect_report(path)
    document = session.scalar(
        select(MatchReportDocument).where(MatchReportDocument.sha256 == manifest.sha256)
    )
    if document is not None and not force:
        existing = session.scalar(
            select(MatchReportExtractionRun)
            .where(
                MatchReportExtractionRun.document_id == document.id,
                MatchReportExtractionRun.pipeline_version == PIPELINE_VERSION,
                MatchReportExtractionRun.status == "completed",
            )
            .order_by(MatchReportExtractionRun.attempt.desc())
        )
        if existing:
            return _summary_from_run(document, existing)

    raw_dir = ROOT_DIR / "data" / "raw" / "match_reports"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"{manifest.sha256}.pdf"
    if not raw_path.exists():
        shutil.copy2(path, raw_path)
    artifact_root = ROOT_DIR / "data" / "processed" / "match_reports"
    bundle = extract_report(raw_path, artifact_root)
    bundle.manifest.source_path = str(raw_path.resolve())
    if dry_run:
        return IngestionSummary(
            sha256=manifest.sha256,
            status=bundle.status,
            dry_run=True,
            artifact_root=bundle.artifact_root,
            page_count=bundle.manifest.page_count,
            quality_score=bundle.quality_score,
            coverage=bundle.coverage,
            counts={key: int(value) for key, value in bundle.stats.items()},
            issues=bundle.issues,
        )
    try:
        run = load_extraction(session, bundle)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return IngestionSummary(
        document_id=run.document_id,
        extraction_run_id=run.id,
        sha256=manifest.sha256,
        status=run.status,
        artifact_root=bundle.artifact_root,
        page_count=bundle.manifest.page_count,
        quality_score=bundle.quality_score,
        coverage=bundle.coverage,
        counts={key: int(value) for key, value in bundle.stats.items()},
        issues=bundle.issues,
    )
