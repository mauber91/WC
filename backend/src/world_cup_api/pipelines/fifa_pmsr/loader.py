from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from world_cup_api.db.models import Match, SquadPlayer, Team
from world_cup_api.db.report_models import (
    MatchReportDocument,
    MatchReportEvent,
    MatchReportExtractionRun,
    MatchReportIssue,
    MatchReportMetricDefinition,
    MatchReportNetworkEdge,
    MatchReportObservation,
    MatchReportPage,
    MatchReportPagePayload,
    MatchReportParticipant,
    MatchReportSpatialFeature,
    MatchReportTimeseriesPoint,
)
from world_cup_api.domain.name_match import normalize_name
from world_cup_api.pipelines.fifa_pmsr.raw import payload_checksum
from world_cup_api.pipelines.fifa_pmsr.types import ExtractionBundle


def _team_map(session: Session) -> dict[str, Team]:
    teams = session.scalars(select(Team)).all()
    result: dict[str, Team] = {}
    for team in teams:
        result[normalize_name(team.name)] = team
        result[normalize_name(team.short_name)] = team
        result[normalize_name(team.fifa_code)] = team
    return result


def _resolve_match(session: Session, bundle: ExtractionBundle, teams: dict[str, Team]) -> Match | None:
    number = bundle.manifest.official_match_number
    if number is None:
        return None
    candidates = session.scalars(select(Match).where(Match.official_match_number == number)).all()
    home = teams.get(normalize_name(bundle.manifest.home_team or ""))
    away = teams.get(normalize_name(bundle.manifest.away_team or ""))
    for candidate in candidates:
        if home and away and {candidate.team_a_id, candidate.team_b_id} == {home.id, away.id}:
            return candidate
    return candidates[0] if len(candidates) == 1 else None


def _metric_definition(
    session: Session,
    cache: dict[str, MatchReportMetricDefinition],
    metric_key: str,
    scope: str,
    unit: str | None,
    numeric: bool,
) -> None:
    if metric_key in cache:
        return
    existing = session.scalar(
        select(MatchReportMetricDefinition).where(MatchReportMetricDefinition.metric_key == metric_key)
    )
    if existing:
        cache[metric_key] = existing
        return
    definition = MatchReportMetricDefinition(
        metric_key=metric_key,
        label=metric_key.replace("_", " ").replace(".", " · ").title(),
        scope=scope,
        unit=unit,
        value_type="numeric" if numeric else "text",
        aggregation="sum" if metric_key.startswith("physical.") else "none",
        definition_version="fifa-pmsr-v1",
    )
    session.add(definition)
    cache[metric_key] = definition


def load_extraction(session: Session, bundle: ExtractionBundle) -> MatchReportExtractionRun:
    """Load a bundle into the current transaction and return its versioned run."""
    teams = _team_map(session)
    document = session.scalar(
        select(MatchReportDocument).where(MatchReportDocument.sha256 == bundle.manifest.sha256)
    )
    match = _resolve_match(session, bundle, teams)
    if document is None:
        document = MatchReportDocument(
            id=str(uuid4()),
            sha256=bundle.manifest.sha256,
            filename=bundle.manifest.filename,
            source_path=bundle.manifest.source_path,
            raw_pdf_uri=bundle.manifest.source_path,
            file_size_bytes=bundle.manifest.file_size_bytes,
            match_id=match.id if match else None,
            official_match_number=bundle.manifest.official_match_number,
            template_key=bundle.manifest.template_key,
            template_version=bundle.template_version,
            page_count=bundle.manifest.page_count,
            pdf_metadata_json=bundle.manifest.metadata,
            status="extracting",
        )
        session.add(document)
        session.flush()
    else:
        document.source_path = bundle.manifest.source_path
        document.file_size_bytes = bundle.manifest.file_size_bytes
        document.match_id = match.id if match else document.match_id
        document.template_key = bundle.manifest.template_key
        document.template_version = bundle.template_version
        document.page_count = bundle.manifest.page_count

    prior_runs = session.scalars(
        select(MatchReportExtractionRun).where(MatchReportExtractionRun.document_id == document.id)
    ).all()
    for prior in prior_runs:
        prior.is_active = False
    session.flush()
    attempt = max((prior.attempt for prior in prior_runs), default=0) + 1
    run = MatchReportExtractionRun(
        id=str(uuid4()),
        document_id=document.id,
        pipeline_version=bundle.pipeline_version,
        template_version=bundle.template_version,
        attempt=attempt,
        status=bundle.status,
        quality_score=bundle.quality_score,
        coverage=bundle.coverage,
        artifact_root=bundle.artifact_root,
        stats_json=bundle.stats,
        error_json=[issue.model_dump(mode="json") for issue in bundle.issues if issue.severity == "error"] or None,
        is_active=True,
        completed_at=datetime.now(timezone.utc),
    )
    session.add(run)
    session.flush()

    page_ids: dict[int, int] = {}
    for page in bundle.pages:
        team = teams.get(normalize_name(page.classification.team_scope or ""))
        page_model = MatchReportPage(
            run_id=run.id,
            document_id=document.id,
            page_number=page.page_number,
            page_type=page.classification.page_type,
            section=page.classification.section,
            team_scope=page.classification.team_scope,
            team_id=team.id if team else None,
            width_points=page.width_points,
            height_points=page.height_points,
            rotation=page.rotation,
            raw_text=page.raw_text,
            render_uri=page.render_uri,
            render_sha256=page.render_sha256,
            classification_confidence=page.classification.confidence,
            raw_element_count=page.element_count,
        )
        session.add(page_model)
        session.flush()
        page_ids[page.page_number] = page_model.id
        for payload_type, elements in page.payloads.items():
            counts = {classification: 0 for classification in ("mapped", "decorative", "unresolved")}
            for element in elements:
                classification = str(element.get("classification", "unresolved"))
                counts[classification] = counts.get(classification, 0) + 1
            session.add(
                MatchReportPagePayload(
                    page_id=page_model.id,
                    payload_type=payload_type,
                    payload_json=elements,
                    element_count=len(elements),
                    mapped_count=counts["mapped"],
                    decorative_count=counts["decorative"],
                    unresolved_count=counts["unresolved"],
                    checksum=payload_checksum(elements),
                )
            )

    squad_by_team_number: dict[tuple[int, int], SquadPlayer] = {}
    for player in session.scalars(select(SquadPlayer)).all():
        squad_by_team_number[(player.team_id, player.squad_number)] = player
    participant_ids: dict[tuple[str, str], int] = {}
    for participant in bundle.participants:
        team = teams.get(normalize_name(participant.team_source_name))
        squad = None
        if team and participant.shirt_number is not None:
            squad = squad_by_team_number.get((team.id, participant.shirt_number))
        participant_model = MatchReportParticipant(
            run_id=run.id,
            page_id=page_ids.get(participant.page_number),
            team_id=team.id if team else None,
            squad_player_id=squad.id if squad else None,
            team_source_name=participant.team_source_name,
            source_name=participant.source_name,
            normalized_name=participant.normalized_name,
            shirt_number=participant.shirt_number,
            position=participant.position,
            formation_role=participant.formation_role,
            is_starter=participant.is_starter,
            is_substitute=participant.is_substitute,
            is_captain=participant.is_captain,
            source_bbox_json=participant.source_bbox,
            source_element_ids_json=participant.source_element_ids,
            method=participant.method,
            confidence=participant.confidence,
        )
        session.add(participant_model)
        session.flush()
        participant_ids[(normalize_name(participant.team_source_name), participant.normalized_name)] = participant_model.id

    def participant_id(team_name: str | None, player_name: str | None) -> int | None:
        if not player_name:
            return None
        team_key = normalize_name(team_name or "")
        normalized = normalize_name(player_name)
        exact = participant_ids.get((team_key, normalized))
        if exact:
            return exact
        for (candidate_team, candidate_name), identifier in participant_ids.items():
            if candidate_team == team_key and (normalized in candidate_name or candidate_name in normalized):
                return identifier
        return None

    metric_cache: dict[str, MatchReportMetricDefinition] = {}
    for observation in bundle.observations:
        team = teams.get(normalize_name(observation.team_source_name or ""))
        _metric_definition(
            session,
            metric_cache,
            observation.metric_key,
            observation.scope,
            observation.unit,
            observation.value_numeric is not None,
        )
        session.add(
            MatchReportObservation(
                run_id=run.id,
                page_id=page_ids[observation.page_number],
                scope=observation.scope,
                team_id=team.id if team else None,
                participant_id=participant_id(observation.team_source_name, observation.participant_name),
                metric_key=observation.metric_key,
                value_numeric=observation.value_numeric,
                value_text=observation.value_text,
                unit=observation.unit,
                period=observation.period,
                phase=observation.phase,
                dimensions_json=observation.dimensions,
                is_explicit_zero=observation.is_explicit_zero,
                is_blank=observation.is_blank,
                source_bbox_json=observation.source_bbox,
                source_element_ids_json=observation.source_element_ids,
                method=observation.method,
                confidence=observation.confidence,
            )
        )

    for event in bundle.events:
        team = teams.get(normalize_name(event.team_source_name or ""))
        session.add(
            MatchReportEvent(
                run_id=run.id,
                page_id=page_ids[event.page_number],
                team_id=team.id if team else None,
                participant_id=participant_id(event.team_source_name, event.participant_name),
                event_type=event.event_type,
                event_number=event.event_number,
                minute=event.minute,
                added_time=event.added_time,
                match_second=event.match_second,
                period=event.period,
                category=event.category,
                outcome=event.outcome,
                body_part=event.body_part,
                raw_start_x=event.raw_start_x,
                raw_start_y=event.raw_start_y,
                raw_end_x=event.raw_end_x,
                raw_end_y=event.raw_end_y,
                norm_start_x=event.norm_start_x,
                norm_start_y=event.norm_start_y,
                norm_end_x=event.norm_end_x,
                norm_end_y=event.norm_end_y,
                pitch_start_x_m=event.pitch_start_x_m,
                pitch_start_y_m=event.pitch_start_y_m,
                pitch_end_x_m=event.pitch_end_x_m,
                pitch_end_y_m=event.pitch_end_y_m,
                coordinate_space=event.coordinate_space,
                attacking_direction=event.attacking_direction,
                length_m=event.length_m,
                angle_degrees=event.angle_degrees,
                attributes_json=event.attributes,
                source_bbox_json=event.source_bbox,
                source_element_ids_json=event.source_element_ids,
                method=event.method,
                confidence=event.confidence,
            )
        )

    for feature in bundle.spatial_features:
        team = teams.get(normalize_name(feature.team_source_name or ""))
        session.add(
            MatchReportSpatialFeature(
                run_id=run.id,
                page_id=page_ids[feature.page_number],
                team_id=team.id if team else None,
                participant_id=participant_id(feature.team_source_name, feature.participant_name),
                feature_type=feature.feature_type,
                geometry_type=feature.geometry_type,
                coordinate_space=feature.coordinate_space,
                raw_geometry_json=feature.raw_geometry,
                normalized_geometry_json=feature.normalized_geometry,
                canonical_geometry_json=feature.canonical_geometry,
                category=feature.category,
                phase=feature.phase,
                value_numeric=feature.value_numeric,
                unit=feature.unit,
                attributes_json=feature.attributes,
                source_element_ids_json=feature.source_element_ids,
                method=feature.method,
                confidence=feature.confidence,
            )
        )

    for edge in bundle.network_edges:
        team = teams.get(normalize_name(edge.team_source_name))
        session.add(
            MatchReportNetworkEdge(
                run_id=run.id,
                page_id=page_ids[edge.page_number],
                team_id=team.id if team else None,
                source_participant_id=participant_id(edge.team_source_name, edge.source_player_name),
                target_participant_id=participant_id(edge.team_source_name, edge.target_player_name),
                source_player_name=edge.source_player_name,
                target_player_name=edge.target_player_name,
                pass_count=edge.pass_count,
                pass_share=edge.pass_share,
                attributes_json=edge.attributes,
                source_bbox_json=edge.source_bbox,
                source_element_ids_json=edge.source_element_ids,
                method=edge.method,
                confidence=edge.confidence,
            )
        )

    for point in bundle.timeseries_points:
        team = teams.get(normalize_name(point.team_source_name))
        session.add(
            MatchReportTimeseriesPoint(
                run_id=run.id,
                page_id=page_ids[point.page_number],
                team_id=team.id if team else None,
                participant_id=participant_id(point.team_source_name, point.participant_name),
                team_source_name=point.team_source_name,
                series_key=point.series_key,
                period=point.period,
                minute=point.minute,
                match_second=point.match_second,
                value=point.value,
                unit=point.unit,
                raw_x=point.raw_x,
                raw_y=point.raw_y,
                attributes_json=point.attributes,
                source_element_ids_json=point.source_element_ids,
                method=point.method,
                confidence=point.confidence,
            )
        )

    for issue in bundle.issues:
        session.add(
            MatchReportIssue(
                run_id=run.id,
                page_id=page_ids.get(issue.page_number) if issue.page_number else None,
                severity=issue.severity,
                code=issue.code,
                message=issue.message,
                artifact_type=issue.artifact_type,
                source_bbox_json=issue.source_bbox,
                source_element_ids_json=issue.source_element_ids,
                evidence_json=issue.evidence,
            )
        )

    document.status = bundle.status
    document.raw_pdf_uri = str(Path(bundle.manifest.source_path).resolve())
    session.flush()
    return run
