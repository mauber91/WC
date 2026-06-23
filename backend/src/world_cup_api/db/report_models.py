from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from world_cup_api.db.base import Base
from world_cup_api.db.models import utcnow


class MatchReportDocument(Base):
    __tablename__ = "match_report_documents"
    __table_args__ = (
        UniqueConstraint("sha256"),
        Index("ix_match_report_documents_match", "match_id"),
        Index("ix_match_report_documents_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    raw_pdf_uri: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    match_id: Mapped[int | None] = mapped_column(ForeignKey("matches.id", ondelete="SET NULL"))
    official_match_number: Mapped[int | None] = mapped_column(Integer)
    template_key: Mapped[str | None] = mapped_column(String(80))
    template_version: Mapped[str | None] = mapped_column(String(40))
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    pdf_metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="inspected")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    runs: Mapped[list[MatchReportExtractionRun]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class MatchReportExtractionRun(Base):
    __tablename__ = "match_report_extraction_runs"
    __table_args__ = (
        UniqueConstraint("document_id", "pipeline_version", "template_version", "attempt"),
        CheckConstraint("quality_score IS NULL OR (quality_score >= 0 AND quality_score <= 1)"),
        CheckConstraint("coverage IS NULL OR (coverage >= 0 AND coverage <= 1)"),
        Index("ix_match_report_runs_document_created", "document_id", "created_at"),
        Index(
            "ux_match_report_runs_active",
            "document_id",
            unique=True,
            sqlite_where=text("is_active = 1"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("match_report_documents.id", ondelete="CASCADE"), nullable=False
    )
    pipeline_version: Mapped[str] = mapped_column(String(40), nullable=False)
    template_version: Mapped[str] = mapped_column(String(40), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(24), default="running", index=True)
    quality_score: Mapped[float | None] = mapped_column(Float)
    coverage: Mapped[float | None] = mapped_column(Float)
    artifact_root: Mapped[str] = mapped_column(Text, nullable=False)
    stats_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    document: Mapped[MatchReportDocument] = relationship(back_populates="runs")
    pages: Mapped[list[MatchReportPage]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class MatchReportPage(Base):
    __tablename__ = "match_report_pages"
    __table_args__ = (
        UniqueConstraint("run_id", "page_number"),
        Index("ix_match_report_pages_run_type", "run_id", "page_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("match_report_extraction_runs.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey("match_report_documents.id", ondelete="CASCADE"), nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    page_type: Mapped[str] = mapped_column(String(64), nullable=False)
    section: Mapped[str | None] = mapped_column(String(64))
    team_scope: Mapped[str | None] = mapped_column(String(80))
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"))
    width_points: Mapped[float] = mapped_column(Float, nullable=False)
    height_points: Mapped[float] = mapped_column(Float, nullable=False)
    rotation: Mapped[int] = mapped_column(Integer, default=0)
    raw_text: Mapped[str] = mapped_column(Text, default="")
    render_uri: Mapped[str] = mapped_column(Text, nullable=False)
    render_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    classification_confidence: Mapped[float] = mapped_column(Float, default=0)
    raw_element_count: Mapped[int] = mapped_column(Integer, default=0)

    run: Mapped[MatchReportExtractionRun] = relationship(back_populates="pages")
    payloads: Mapped[list[MatchReportPagePayload]] = relationship(
        back_populates="page", cascade="all, delete-orphan"
    )


class MatchReportPagePayload(Base):
    __tablename__ = "match_report_page_payloads"
    __table_args__ = (
        UniqueConstraint("page_id", "payload_type"),
        Index("ix_match_report_payloads_page", "page_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int] = mapped_column(
        ForeignKey("match_report_pages.id", ondelete="CASCADE"), nullable=False
    )
    payload_type: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    element_count: Mapped[int] = mapped_column(Integer, default=0)
    mapped_count: Mapped[int] = mapped_column(Integer, default=0)
    decorative_count: Mapped[int] = mapped_column(Integer, default=0)
    unresolved_count: Mapped[int] = mapped_column(Integer, default=0)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)

    page: Mapped[MatchReportPage] = relationship(back_populates="payloads")


class MatchReportParticipant(Base):
    __tablename__ = "match_report_participants"
    __table_args__ = (
        UniqueConstraint("run_id", "team_source_name", "shirt_number", "source_name"),
        Index("ix_match_report_participants_run_team", "run_id", "team_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("match_report_extraction_runs.id", ondelete="CASCADE"), nullable=False
    )
    page_id: Mapped[int | None] = mapped_column(
        ForeignKey("match_report_pages.id", ondelete="SET NULL")
    )
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"))
    squad_player_id: Mapped[int | None] = mapped_column(
        ForeignKey("squad_players.id", ondelete="SET NULL")
    )
    team_source_name: Mapped[str] = mapped_column(String(100), nullable=False)
    source_name: Mapped[str] = mapped_column(String(160), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(160), nullable=False)
    shirt_number: Mapped[int | None] = mapped_column(Integer)
    position: Mapped[str | None] = mapped_column(String(24))
    formation_role: Mapped[str | None] = mapped_column(String(32))
    is_starter: Mapped[bool | None] = mapped_column(Boolean)
    is_substitute: Mapped[bool | None] = mapped_column(Boolean)
    is_captain: Mapped[bool] = mapped_column(Boolean, default=False)
    source_bbox_json: Mapped[list[float] | None] = mapped_column(JSON)
    source_element_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    method: Mapped[str] = mapped_column(String(32), default="text")
    confidence: Mapped[float] = mapped_column(Float, default=0)


class MatchReportMetricDefinition(Base):
    __tablename__ = "match_report_metric_definitions"
    __table_args__ = (UniqueConstraint("metric_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    metric_key: Mapped[str] = mapped_column(String(120), nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    scope: Mapped[str] = mapped_column(String(24), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(32))
    value_type: Mapped[str] = mapped_column(String(20), nullable=False)
    aggregation: Mapped[str] = mapped_column(String(32), default="none")
    description: Mapped[str | None] = mapped_column(Text)
    definition_version: Mapped[str] = mapped_column(String(32), default="1")


class MatchReportObservation(Base):
    __tablename__ = "match_report_observations"
    __table_args__ = (
        Index("ix_match_report_observations_run_metric", "run_id", "metric_key"),
        Index("ix_match_report_observations_participant", "participant_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("match_report_extraction_runs.id", ondelete="CASCADE"), nullable=False
    )
    page_id: Mapped[int] = mapped_column(
        ForeignKey("match_report_pages.id", ondelete="CASCADE"), nullable=False
    )
    scope: Mapped[str] = mapped_column(String(24), nullable=False)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"))
    participant_id: Mapped[int | None] = mapped_column(
        ForeignKey("match_report_participants.id", ondelete="SET NULL")
    )
    metric_key: Mapped[str] = mapped_column(String(120), nullable=False)
    value_numeric: Mapped[float | None] = mapped_column(Float)
    value_text: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(String(32))
    period: Mapped[str | None] = mapped_column(String(20))
    phase: Mapped[str | None] = mapped_column(String(40))
    dimensions_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    is_explicit_zero: Mapped[bool] = mapped_column(Boolean, default=False)
    is_blank: Mapped[bool] = mapped_column(Boolean, default=False)
    source_bbox_json: Mapped[list[float] | None] = mapped_column(JSON)
    source_element_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    method: Mapped[str] = mapped_column(String(32), default="text")
    confidence: Mapped[float] = mapped_column(Float, default=0)


class MatchReportEvent(Base):
    __tablename__ = "match_report_events"
    __table_args__ = (
        Index("ix_match_report_events_run_type", "run_id", "event_type"),
        Index("ix_match_report_events_participant", "participant_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("match_report_extraction_runs.id", ondelete="CASCADE"), nullable=False
    )
    page_id: Mapped[int] = mapped_column(
        ForeignKey("match_report_pages.id", ondelete="CASCADE"), nullable=False
    )
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"))
    participant_id: Mapped[int | None] = mapped_column(
        ForeignKey("match_report_participants.id", ondelete="SET NULL")
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_number: Mapped[int | None] = mapped_column(Integer)
    minute: Mapped[int | None] = mapped_column(Integer)
    added_time: Mapped[int | None] = mapped_column(Integer)
    match_second: Mapped[int | None] = mapped_column(Integer)
    period: Mapped[str | None] = mapped_column(String(20))
    category: Mapped[str | None] = mapped_column(String(40))
    outcome: Mapped[str | None] = mapped_column(String(40))
    body_part: Mapped[str | None] = mapped_column(String(40))
    raw_start_x: Mapped[float | None] = mapped_column(Float)
    raw_start_y: Mapped[float | None] = mapped_column(Float)
    raw_end_x: Mapped[float | None] = mapped_column(Float)
    raw_end_y: Mapped[float | None] = mapped_column(Float)
    norm_start_x: Mapped[float | None] = mapped_column(Float)
    norm_start_y: Mapped[float | None] = mapped_column(Float)
    norm_end_x: Mapped[float | None] = mapped_column(Float)
    norm_end_y: Mapped[float | None] = mapped_column(Float)
    pitch_start_x_m: Mapped[float | None] = mapped_column(Float)
    pitch_start_y_m: Mapped[float | None] = mapped_column(Float)
    pitch_end_x_m: Mapped[float | None] = mapped_column(Float)
    pitch_end_y_m: Mapped[float | None] = mapped_column(Float)
    coordinate_space: Mapped[str | None] = mapped_column(String(24))
    attacking_direction: Mapped[str | None] = mapped_column(String(16))
    length_m: Mapped[float | None] = mapped_column(Float)
    angle_degrees: Mapped[float | None] = mapped_column(Float)
    attributes_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    source_bbox_json: Mapped[list[float] | None] = mapped_column(JSON)
    source_element_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    method: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0)


class MatchReportSpatialFeature(Base):
    __tablename__ = "match_report_spatial_features"
    __table_args__ = (Index("ix_match_report_spatial_run_type", "run_id", "feature_type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("match_report_extraction_runs.id", ondelete="CASCADE"), nullable=False
    )
    page_id: Mapped[int] = mapped_column(
        ForeignKey("match_report_pages.id", ondelete="CASCADE"), nullable=False
    )
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"))
    participant_id: Mapped[int | None] = mapped_column(
        ForeignKey("match_report_participants.id", ondelete="SET NULL")
    )
    feature_type: Mapped[str] = mapped_column(String(64), nullable=False)
    geometry_type: Mapped[str] = mapped_column(String(24), nullable=False)
    coordinate_space: Mapped[str] = mapped_column(String(24), nullable=False)
    raw_geometry_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    normalized_geometry_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    canonical_geometry_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    category: Mapped[str | None] = mapped_column(String(40))
    phase: Mapped[str | None] = mapped_column(String(40))
    value_numeric: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(32))
    attributes_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    source_element_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    method: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0)


class MatchReportNetworkEdge(Base):
    __tablename__ = "match_report_network_edges"
    __table_args__ = (
        UniqueConstraint("run_id", "page_id", "source_participant_id", "target_participant_id"),
        Index("ix_match_report_network_run_team", "run_id", "team_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("match_report_extraction_runs.id", ondelete="CASCADE"), nullable=False
    )
    page_id: Mapped[int] = mapped_column(
        ForeignKey("match_report_pages.id", ondelete="CASCADE"), nullable=False
    )
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"))
    source_participant_id: Mapped[int | None] = mapped_column(
        ForeignKey("match_report_participants.id", ondelete="SET NULL")
    )
    target_participant_id: Mapped[int | None] = mapped_column(
        ForeignKey("match_report_participants.id", ondelete="SET NULL")
    )
    source_player_name: Mapped[str] = mapped_column(String(160), nullable=False)
    target_player_name: Mapped[str] = mapped_column(String(160), nullable=False)
    pass_count: Mapped[int] = mapped_column(Integer, nullable=False)
    pass_share: Mapped[float | None] = mapped_column(Float)
    attributes_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    source_bbox_json: Mapped[list[float] | None] = mapped_column(JSON)
    source_element_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    method: Mapped[str] = mapped_column(String(32), default="table")
    confidence: Mapped[float] = mapped_column(Float, default=0)


class MatchReportTimeseriesPoint(Base):
    __tablename__ = "match_report_timeseries_points"
    __table_args__ = (
        UniqueConstraint("run_id", "page_id", "series_key", "team_source_name", "match_second"),
        Index("ix_match_report_timeseries_run_series", "run_id", "series_key", "match_second"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("match_report_extraction_runs.id", ondelete="CASCADE"), nullable=False
    )
    page_id: Mapped[int] = mapped_column(
        ForeignKey("match_report_pages.id", ondelete="CASCADE"), nullable=False
    )
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"))
    participant_id: Mapped[int | None] = mapped_column(
        ForeignKey("match_report_participants.id", ondelete="SET NULL")
    )
    team_source_name: Mapped[str] = mapped_column(String(100), default="")
    series_key: Mapped[str] = mapped_column(String(120), nullable=False)
    period: Mapped[str | None] = mapped_column(String(20))
    minute: Mapped[int | None] = mapped_column(Integer)
    match_second: Mapped[int] = mapped_column(Integer, nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(32))
    raw_x: Mapped[float | None] = mapped_column(Float)
    raw_y: Mapped[float | None] = mapped_column(Float)
    attributes_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    source_element_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    method: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0)


class MatchReportIssue(Base):
    __tablename__ = "match_report_issues"
    __table_args__ = (
        Index("ix_match_report_issues_run_severity", "run_id", "severity"),
        Index("ix_match_report_issues_unresolved", "run_id", "is_resolved"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("match_report_extraction_runs.id", ondelete="CASCADE"), nullable=False
    )
    page_id: Mapped[int | None] = mapped_column(
        ForeignKey("match_report_pages.id", ondelete="CASCADE")
    )
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_type: Mapped[str | None] = mapped_column(String(32))
    source_bbox_json: Mapped[list[float] | None] = mapped_column(JSON)
    source_element_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolution_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


__all__ = [
    "MatchReportDocument",
    "MatchReportEvent",
    "MatchReportExtractionRun",
    "MatchReportIssue",
    "MatchReportMetricDefinition",
    "MatchReportNetworkEdge",
    "MatchReportObservation",
    "MatchReportPage",
    "MatchReportPagePayload",
    "MatchReportParticipant",
    "MatchReportSpatialFeature",
    "MatchReportTimeseriesPoint",
]
