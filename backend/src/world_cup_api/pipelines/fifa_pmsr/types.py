from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class PipelineModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DocumentManifest(PipelineModel):
    source_path: str
    filename: str
    sha256: str
    file_size_bytes: int
    page_count: int
    page_sizes: list[list[float]]
    encrypted: bool
    pdf_version: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    template_key: str | None = None
    template_version: str | None = None
    template_confidence: float = 0.0
    official_match_number: int | None = None
    home_team: str | None = None
    away_team: str | None = None
    home_score: int | None = None
    away_score: int | None = None
    match_date: str | None = None
    kickoff_time: str | None = None
    venue: str | None = None
    inspected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PageClassification(PipelineModel):
    page_type: str
    section: str | None = None
    team_scope: str | None = None
    confidence: float
    matched_anchors: list[str] = Field(default_factory=list)


class RawPage(PipelineModel):
    page_number: int
    width_points: float
    height_points: float
    rotation: int = 0
    raw_text: str = ""
    render_uri: str
    render_sha256: str
    classification: PageClassification
    payloads: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)

    @property
    def element_count(self) -> int:
        return sum(len(elements) for elements in self.payloads.values())


class ParticipantRecord(PipelineModel):
    page_number: int
    team_source_name: str
    source_name: str
    normalized_name: str
    shirt_number: int | None = None
    position: str | None = None
    formation_role: str | None = None
    is_starter: bool | None = None
    is_substitute: bool | None = None
    is_captain: bool = False
    source_bbox: list[float] | None = None
    source_element_ids: list[str] = Field(default_factory=list)
    method: str = "text"
    confidence: float = 0.0


class ObservationRecord(PipelineModel):
    page_number: int
    scope: Literal["match", "team", "player", "table_cell", "document"]
    metric_key: str
    team_source_name: str | None = None
    participant_name: str | None = None
    value_numeric: float | None = None
    value_text: str | None = None
    unit: str | None = None
    period: str | None = None
    phase: str | None = None
    dimensions: dict[str, Any] = Field(default_factory=dict)
    is_explicit_zero: bool = False
    is_blank: bool = False
    source_bbox: list[float] | None = None
    source_element_ids: list[str] = Field(default_factory=list)
    method: str = "text"
    confidence: float = 0.0


class EventRecord(PipelineModel):
    page_number: int
    event_type: str
    team_source_name: str | None = None
    participant_name: str | None = None
    event_number: int | None = None
    minute: int | None = None
    added_time: int | None = None
    match_second: int | None = None
    period: str | None = None
    category: str | None = None
    outcome: str | None = None
    body_part: str | None = None
    raw_start_x: float | None = None
    raw_start_y: float | None = None
    raw_end_x: float | None = None
    raw_end_y: float | None = None
    norm_start_x: float | None = None
    norm_start_y: float | None = None
    norm_end_x: float | None = None
    norm_end_y: float | None = None
    pitch_start_x_m: float | None = None
    pitch_start_y_m: float | None = None
    pitch_end_x_m: float | None = None
    pitch_end_y_m: float | None = None
    coordinate_space: str | None = None
    attacking_direction: str | None = None
    length_m: float | None = None
    angle_degrees: float | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    source_bbox: list[float] | None = None
    source_element_ids: list[str] = Field(default_factory=list)
    method: str
    confidence: float


class SpatialFeatureRecord(PipelineModel):
    page_number: int
    feature_type: str
    geometry_type: str
    coordinate_space: str
    team_source_name: str | None = None
    participant_name: str | None = None
    raw_geometry: dict[str, Any]
    normalized_geometry: dict[str, Any] | None = None
    canonical_geometry: dict[str, Any] | None = None
    category: str | None = None
    phase: str | None = None
    value_numeric: float | None = None
    unit: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    source_element_ids: list[str] = Field(default_factory=list)
    method: str
    confidence: float


class NetworkEdgeRecord(PipelineModel):
    page_number: int
    team_source_name: str
    source_player_name: str
    target_player_name: str
    pass_count: int
    pass_share: float | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    source_bbox: list[float] | None = None
    source_element_ids: list[str] = Field(default_factory=list)
    method: str = "table"
    confidence: float = 0.0


class TimeseriesPointRecord(PipelineModel):
    page_number: int
    series_key: str
    team_source_name: str = ""
    participant_name: str | None = None
    period: str | None = None
    minute: int | None = None
    match_second: int
    value: float
    unit: str | None = None
    raw_x: float | None = None
    raw_y: float | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    source_element_ids: list[str] = Field(default_factory=list)
    method: str
    confidence: float


class IssueRecord(PipelineModel):
    page_number: int | None = None
    severity: Literal["info", "warning", "error"]
    code: str
    message: str
    artifact_type: str | None = None
    source_bbox: list[float] | None = None
    source_element_ids: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)


class ExtractionBundle(PipelineModel):
    manifest: DocumentManifest
    pipeline_version: str
    template_version: str
    artifact_root: str
    pages: list[RawPage] = Field(default_factory=list)
    participants: list[ParticipantRecord] = Field(default_factory=list)
    observations: list[ObservationRecord] = Field(default_factory=list)
    events: list[EventRecord] = Field(default_factory=list)
    spatial_features: list[SpatialFeatureRecord] = Field(default_factory=list)
    network_edges: list[NetworkEdgeRecord] = Field(default_factory=list)
    timeseries_points: list[TimeseriesPointRecord] = Field(default_factory=list)
    issues: list[IssueRecord] = Field(default_factory=list)
    quality_score: float = 0.0
    coverage: float = 0.0
    status: Literal["completed", "needs_review", "failed"] = "needs_review"
    stats: dict[str, Any] = Field(default_factory=dict)

    def write_json(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.model_dump_json(indent=2), encoding="utf-8")
        return target


class IngestionSummary(PipelineModel):
    document_id: str | None = None
    extraction_run_id: str | None = None
    sha256: str
    status: str
    reused: bool = False
    dry_run: bool = False
    artifact_root: str
    page_count: int
    quality_score: float
    coverage: float
    counts: dict[str, int] = Field(default_factory=dict)
    issues: list[IssueRecord] = Field(default_factory=list)
