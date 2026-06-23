from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select
from sqlalchemy.orm import Session

from world_cup_api.db.report_models import (
    MatchReportDocument,
    MatchReportEvent,
    MatchReportExtractionRun,
    MatchReportIssue,
    MatchReportNetworkEdge,
    MatchReportObservation,
    MatchReportPage,
    MatchReportPagePayload,
    MatchReportParticipant,
    MatchReportSpatialFeature,
    MatchReportTimeseriesPoint,
)


def _value(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


def _row(model: Any) -> dict[str, Any]:
    return {
        column.key: _value(getattr(model, column.key))
        for column in sa_inspect(model.__class__).columns
    }


def _datasets(session: Session, document_id: str) -> dict[str, list[dict[str, Any]]]:
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
    pages = session.scalars(select(MatchReportPage).where(MatchReportPage.run_id == run.id)).all()
    page_ids = [page.id for page in pages]
    return {
        "documents": [_row(document)],
        "extraction_runs": [_row(run)],
        "pages": [_row(value) for value in pages],
        "page_payloads": [
            _row(value)
            for value in session.scalars(
                select(MatchReportPagePayload).where(MatchReportPagePayload.page_id.in_(page_ids))
            ).all()
        ],
        "participants": [
            _row(value)
            for value in session.scalars(
                select(MatchReportParticipant).where(MatchReportParticipant.run_id == run.id)
            ).all()
        ],
        "observations": [
            _row(value)
            for value in session.scalars(
                select(MatchReportObservation).where(MatchReportObservation.run_id == run.id)
            ).all()
        ],
        "events": [
            _row(value)
            for value in session.scalars(select(MatchReportEvent).where(MatchReportEvent.run_id == run.id)).all()
        ],
        "spatial_features": [
            _row(value)
            for value in session.scalars(
                select(MatchReportSpatialFeature).where(MatchReportSpatialFeature.run_id == run.id)
            ).all()
        ],
        "network_edges": [
            _row(value)
            for value in session.scalars(
                select(MatchReportNetworkEdge).where(MatchReportNetworkEdge.run_id == run.id)
            ).all()
        ],
        "timeseries_points": [
            _row(value)
            for value in session.scalars(
                select(MatchReportTimeseriesPoint).where(MatchReportTimeseriesPoint.run_id == run.id)
            ).all()
        ],
        "issues": [
            _row(value)
            for value in session.scalars(select(MatchReportIssue).where(MatchReportIssue.run_id == run.id)).all()
        ],
    }


def export_document(
    session: Session,
    document_id: str,
    output_dir: str | Path,
    format: str,
) -> list[Path]:
    if format not in {"jsonl", "parquet"}:
        raise ValueError("format must be jsonl or parquet")
    target = Path(output_dir).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    datasets = _datasets(session, document_id)
    outputs: list[Path] = []
    for name, rows in datasets.items():
        path = target / f"{name}.{format}"
        if format == "jsonl":
            with path.open("w", encoding="utf-8") as stream:
                for row in rows:
                    stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        else:
            parquet_rows = [
                {
                    key: json.dumps(value, ensure_ascii=False, sort_keys=True)
                    if isinstance(value, dict | list)
                    else value
                    for key, value in row.items()
                }
                for row in rows
            ]
            table = pa.Table.from_pylist(parquet_rows) if parquet_rows else pa.table({"_empty": pa.array([], type=pa.string())})
            pq.write_table(table, path, compression="zstd")
        outputs.append(path)
    return outputs
