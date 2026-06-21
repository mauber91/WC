from __future__ import annotations

import json
from pathlib import Path

import pyarrow.parquet as pq
from sqlalchemy import func, select

from world_cup_api.db.report_models import (
    MatchReportDocument,
    MatchReportEvent,
    MatchReportExtractionRun,
    MatchReportObservation,
    MatchReportPage,
    MatchReportPagePayload,
)
from world_cup_api.pipelines.fifa_pmsr.export import export_document
from world_cup_api.pipelines.fifa_pmsr.loader import load_extraction
from world_cup_api.pipelines.fifa_pmsr.service import ingest_report
from world_cup_api.pipelines.fifa_pmsr.types import (
    DocumentManifest,
    EventRecord,
    ExtractionBundle,
    ObservationRecord,
    PageClassification,
    RawPage,
)


def _bundle(tmp_path: Path) -> ExtractionBundle:
    render = tmp_path / "page.png"
    render.write_bytes(b"png")
    return ExtractionBundle(
        manifest=DocumentManifest(
            source_path=str(tmp_path / "report.pdf"),
            filename="report.pdf",
            sha256="a" * 64,
            file_size_bytes=100,
            page_count=1,
            page_sizes=[[960, 540]],
            encrypted=False,
            template_key="fifa_pmsr_2026",
            template_version="2026.1",
            template_confidence=1,
            official_match_number=29,
            home_team="Brazil",
            away_team="Haiti",
            home_score=3,
            away_score=0,
            match_date="19 June 2026",
            kickoff_time="20:30",
            venue="Philadelphia Stadium",
        ),
        pipeline_version="fifa-pmsr-v1",
        template_version="2026.1",
        artifact_root=str(tmp_path),
        pages=[
            RawPage(
                page_number=1,
                width_points=960,
                height_points=540,
                raw_text="test",
                render_uri=str(render),
                render_sha256="b" * 64,
                classification=PageClassification(page_type="cover", confidence=1),
                payloads={
                    "text_spans": [
                        {
                            "id": "p1:word:0",
                            "text": "test",
                            "classification": "mapped",
                            "mapped_by": "test",
                        }
                    ]
                },
            )
        ],
        observations=[
            ObservationRecord(
                page_number=1,
                scope="team",
                team_source_name="Brazil",
                metric_key="summary.possession",
                value_numeric=49,
                unit="%",
                confidence=1,
            )
        ],
        events=[
            EventRecord(
                page_number=1,
                event_type="attempt",
                team_source_name="Brazil",
                minute=10,
                method="test",
                confidence=1,
            )
        ],
        quality_score=1,
        coverage=1,
        status="completed",
        stats={"pages": 1, "observations": 1, "events": 1},
    )


def test_load_is_versioned_and_exports_jsonl_and_parquet(db_session, tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    first = load_extraction(db_session, bundle)
    db_session.commit()
    second = load_extraction(db_session, bundle)
    db_session.commit()

    assert first.document_id == second.document_id
    assert first.id != second.id
    assert first.is_active is False
    assert second.is_active is True
    assert db_session.scalar(select(func.count()).select_from(MatchReportDocument)) == 1
    assert db_session.scalar(select(func.count()).select_from(MatchReportExtractionRun)) == 2
    assert db_session.scalar(select(func.count()).select_from(MatchReportPage)) == 2
    assert db_session.scalar(select(func.count()).select_from(MatchReportPagePayload)) == 2
    assert db_session.scalar(select(func.count()).select_from(MatchReportObservation)) == 2
    assert db_session.scalar(select(func.count()).select_from(MatchReportEvent)) == 2

    json_files = export_document(db_session, second.document_id, tmp_path / "json", "jsonl")
    parquet_files = export_document(db_session, second.document_id, tmp_path / "parquet", "parquet")
    assert {path.stem for path in json_files} == {path.stem for path in parquet_files}
    observation_json = next(path for path in json_files if path.stem == "observations")
    observation_parquet = next(path for path in parquet_files if path.stem == "observations")
    assert len(observation_json.read_text().splitlines()) == pq.read_table(observation_parquet).num_rows == 1
    assert json.loads(observation_json.read_text().splitlines()[0])["metric_key"] == "summary.possession"


def test_ingest_is_idempotent_for_same_hash_and_pipeline(
    db_session, tmp_path: Path, monkeypatch
) -> None:
    import world_cup_api.pipelines.fifa_pmsr.service as service

    source = tmp_path / "source.pdf"
    source.write_bytes(b"not-used-by-mocked-inspector")
    bundle = _bundle(tmp_path)
    bundle.manifest.source_path = str(source)
    calls = 0

    def fake_extract(path, artifact_root):
        nonlocal calls
        calls += 1
        bundle.artifact_root = str(artifact_root)
        return bundle

    monkeypatch.setattr(service, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(service, "inspect_report", lambda path: bundle.manifest)
    monkeypatch.setattr(service, "extract_report", fake_extract)

    first = ingest_report(db_session, source)
    second = ingest_report(db_session, source)

    assert first.reused is False
    assert second.reused is True
    assert first.document_id == second.document_id
    assert calls == 1
    assert (tmp_path / "data" / "raw" / "match_reports" / f"{'a' * 64}.pdf").exists()
