from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from world_cup_api.db.report_models import (
    MatchReportDocument,
    MatchReportExtractionRun,
    MatchReportIssue,
    MatchReportPage,
    MatchReportPagePayload,
)


def validate_document(session: Session, document_id: str) -> dict[str, object]:
    document = session.get(MatchReportDocument, document_id)
    if document is None:
        raise KeyError(f"No match report document {document_id}")
    run = session.scalar(
        select(MatchReportExtractionRun)
        .where(
            MatchReportExtractionRun.document_id == document_id,
            MatchReportExtractionRun.is_active.is_(True),
        )
        .order_by(MatchReportExtractionRun.attempt.desc())
    )
    if run is None:
        raise KeyError(f"Document {document_id} has no active extraction")
    pages = session.scalar(
        select(func.count()).select_from(MatchReportPage).where(MatchReportPage.run_id == run.id)
    )
    unresolved = session.scalar(
        select(func.coalesce(func.sum(MatchReportPagePayload.unresolved_count), 0))
        .join(MatchReportPage)
        .where(MatchReportPage.run_id == run.id)
    )
    issues = session.scalars(select(MatchReportIssue).where(MatchReportIssue.run_id == run.id)).all()
    return {
        "document_id": document.id,
        "run_id": run.id,
        "status": run.status,
        "quality_score": run.quality_score,
        "coverage": run.coverage,
        "page_count": pages,
        "expected_page_count": document.page_count,
        "unresolved_artifacts": unresolved,
        "valid": pages == document.page_count and not any(issue.severity == "error" for issue in issues),
        "issues": [
            {
                "severity": issue.severity,
                "page_id": issue.page_id,
                "code": issue.code,
                "message": issue.message,
                "resolved": issue.is_resolved,
            }
            for issue in issues
        ],
    }
