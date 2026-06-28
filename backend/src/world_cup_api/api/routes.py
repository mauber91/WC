from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from world_cup_api.api.dependencies import require_admin
from world_cup_api.api.schemas import ResultInput, SimulationInput, SimulationStatus
from world_cup_api.config import Settings, get_settings
from world_cup_api.db.models import (
    BookmakerOdds, Group, Match, PredictionMarketPrice, Simulation, SimulationBracketResult,
    SimulationGroupResult, SimulationTeamR32Rival, SimulationTeamResult, Team, TournamentTeam, IngestionRun,
)
from world_cup_api.db.report_models import (
    MatchReportDocument,
    MatchReportEvent,
    MatchReportExtractionRun,
    MatchReportIssue,
    MatchReportNetworkEdge,
    MatchReportObservation,
    MatchReportPage,
    MatchReportParticipant,
    MatchReportSpatialFeature,
    MatchReportTimeseriesPoint,
)
from world_cup_api.db.session import get_db
from world_cup_api.jobs.scheduler import schedule_simulation
from world_cup_api.services.predictions import forecast_match, forecast_matches
from world_cup_api.services.results import remove_current_result, revise_result
from world_cup_api.services.champion_market_sync import sync_wc_champion_markets
from world_cup_api.services.market_sync import sync_upcoming_markets
from world_cup_api.services.tournament_refresh import refresh_tournament_data
from world_cup_api.services.simulation_coverage import compute_result_coverage
from world_cup_api.services.power_rankings import power_rankings
from world_cup_api.services.simulations import create_simulation
from world_cup_api.domain.teams import team_slug
from world_cup_api.services.teams import resolve_team, team_detail
from world_cup_api.services.tournament import current_third_place, group_list, group_standings, list_matches
from world_cup_api.ingestion.csv_import import commit_import, preview_import


router = APIRouter(prefix="/api/v1")


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "time": datetime.now(timezone.utc)}


@router.get("/teams")
def teams(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(select(Team, TournamentTeam).join(TournamentTeam).order_by(Team.name)).all()
    return [{"id": team.id, "slug": team_slug(team.name), "fifa_code": team.fifa_code, "name": team.name, "short_name": team.short_name,
             "confederation": team.confederation, "country_code": team.country_code, "group_id": membership.group_id,
             "is_host": membership.is_host} for team, membership in rows]


@router.get("/teams/{team_ref}")
def team_detail_route(team_ref: str, db: Session = Depends(get_db)) -> dict:
    try:
        return team_detail(db, team_ref)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/teams/{team_ref}/forecast")
def team_forecast_route(team_ref: str, simulation_id: str, db: Session = Depends(get_db)) -> dict:
    try:
        team = resolve_team(db, team_ref)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    run = _run_or_404(db, simulation_id, get_settings())
    row = db.get(SimulationTeamResult, (simulation_id, team.id))
    if not row:
        raise HTTPException(404, "Team forecast not found")
    payload = _team_probability(row, run)
    payload["r32_rivals"] = _team_r32_rivals(db, simulation_id, team.id, row)
    return payload


@router.get("/groups")
def groups(db: Session = Depends(get_db)) -> list[dict]:
    return group_list(db)


@router.get("/groups/third-place")
def third_place(db: Session = Depends(get_db)) -> dict:
    table = current_third_place(db)
    return {"provisional": table.provisional, "warnings": table.warnings,
            "rows": [_standing_dict(row) for row in table.rows]}


@router.get("/groups/{code}/standings")
def standings(code: str, db: Session = Depends(get_db)) -> dict:
    try:
        group, table = group_standings(db, code)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"group": {"id": group.id, "code": group.code, "display_name": group.display_name},
            "as_of": datetime.now(timezone.utc), "provisional": table.provisional,
            "warnings": table.warnings, "rows": [_standing_dict(row) for row in table.rows]}


@router.get("/groups/{code}/projection")
def group_projection(code: str, simulation_id: str, db: Session = Depends(get_db)) -> dict:
    run = _run_or_404(db, simulation_id, get_settings())
    group = db.scalar(select(Group).where(Group.code == code.upper()))
    if not group:
        raise HTTPException(404, "Group not found")
    order = db.scalar(select(SimulationGroupResult).where(
        SimulationGroupResult.simulation_id == simulation_id, SimulationGroupResult.group_id == group.id,
    ).order_by(SimulationGroupResult.occurrence_count.desc()).limit(1))
    team_rows = db.scalars(select(SimulationTeamResult).join(TournamentTeam, TournamentTeam.team_id == SimulationTeamResult.team_id).where(
        SimulationTeamResult.simulation_id == simulation_id, TournamentTeam.group_id == group.id,
    )).all()
    return {"simulation_id": simulation_id, "iterations": run.progress_iterations,
            "most_likely_order": [order.rank_1_team_id, order.rank_2_team_id, order.rank_3_team_id, order.rank_4_team_id] if order else [],
            "order_probability": order.occurrence_count / run.progress_iterations if order and run.progress_iterations else 0,
            "teams": [_team_probability(row, run) for row in team_rows]}


@router.get("/matches")
def matches(group: str | None = None, db: Session = Depends(get_db)) -> list[dict]:
    return list_matches(db, group)


@router.get("/matches/predictions")
def match_predictions(
    match_ids: list[int] | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[int, dict]:
    ids = match_ids
    if ids is None:
        ids = list(db.scalars(select(Match.id).where(Match.team_a_id.is_not(None), Match.team_b_id.is_not(None))))
    return {
        match_id: _match_prediction_payload(match, forecast, sources, has_external_market)
        for match_id, (match, forecast, sources, has_external_market) in forecast_matches(db, ids).items()
    }


@router.get("/matches/{match_id}")
def match_detail(match_id: int, db: Session = Depends(get_db)) -> dict:
    found = next((item for item in list_matches(db) if item["id"] == match_id), None)
    if not found:
        raise HTTPException(404, "Match not found")
    return found


@router.get("/matches/{match_id}/prediction")
def match_prediction(match_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        match, forecast, sources, has_external_market = forecast_match(db, match_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    return _match_prediction_payload(match, forecast, sources, has_external_market)


@router.get("/matches/{match_id}/odds")
def match_odds(match_id: int, db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(BookmakerOdds).where(BookmakerOdds.match_id == match_id).order_by(BookmakerOdds.snapshot_at.desc())).all()
    return [{"bookmaker": row.bookmaker, "market_type": row.market_type, "selection": row.selection,
             "decimal_odds": row.decimal_odds, "snapshot_at": row.snapshot_at} for row in rows]


@router.get("/matches/{match_id}/prediction-markets")
def market_prices(match_id: int, db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(PredictionMarketPrice).where(PredictionMarketPrice.match_id == match_id)
                      .order_by(PredictionMarketPrice.snapshot_at.desc())).all()
    return [{"platform": row.platform, "market_type": row.market_type, "selection": row.selection,
             "yes_price": row.yes_price, "best_bid": row.best_bid, "best_ask": row.best_ask,
             "volume": row.volume, "snapshot_at": row.snapshot_at} for row in rows]


@router.get("/published")
def published_forecast(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict:
    if not settings.published_simulation_id:
        raise HTTPException(404, "Published forecast is not configured")
    run = _run_or_404(db, settings.published_simulation_id, settings)
    if run.status != "completed":
        raise HTTPException(503, "Published forecast is not ready")
    return {
        "simulation_id": run.id,
        "iterations": run.iterations,
        "seed": run.seed,
        "input_cutoff_at": run.input_cutoff_at,
        "model_version": run.model_version,
        "ruleset_version": run.ruleset_version,
        "completed_at": run.completed_at,
        "duration_ms": run.duration_ms,
        "result_coverage": compute_result_coverage(db, run).to_dict(),
    }


@router.post("/simulations", response_model=SimulationStatus, status_code=status.HTTP_202_ACCEPTED)
def start_simulation(
    payload: SimulationInput,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> SimulationStatus:
    if not settings.simulations_enabled:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Simulations are disabled on this server")
    run = create_simulation(db, payload.iterations, payload.seed, payload.force)
    if run.status == "queued":
        schedule_simulation(run.id)
    return _simulation_status(db, run)


@router.get("/simulations", response_model=list[SimulationStatus])
def simulations(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> list[SimulationStatus]:
    if settings.published_simulation_id:
        run = db.get(Simulation, settings.published_simulation_id)
        if not run:
            raise HTTPException(404, "Published simulation not found")
        return [_simulation_status(db, run)]
    runs = list(db.scalars(select(Simulation).order_by(Simulation.created_at.desc()).limit(50)))
    return [_simulation_status(db, run) for run in runs]


@router.get("/simulations/{simulation_id}", response_model=SimulationStatus)
def simulation_status(simulation_id: str, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> SimulationStatus:
    return _simulation_status(db, _run_or_404(db, simulation_id, settings))


@router.post("/simulations/{simulation_id}/cancel", response_model=SimulationStatus)
def cancel_simulation(
    simulation_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> SimulationStatus:
    if not settings.simulations_enabled:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Simulations are disabled on this server")
    run = _run_or_404(db, simulation_id, settings)
    run.cancel_requested = True
    db.commit()
    db.refresh(run)
    return _simulation_status(db, run)


@router.get("/simulations/{simulation_id}/teams")
def simulation_teams(simulation_id: str, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> list[dict]:
    run = _run_or_404(db, simulation_id, settings)
    rows = db.execute(select(SimulationTeamResult, Team).join(Team, Team.id == SimulationTeamResult.team_id).where(
        SimulationTeamResult.simulation_id == simulation_id)).all()
    return [{**_team_probability(row, run), "name": team.name, "fifa_code": team.fifa_code} for row, team in rows]


@router.get("/simulations/{simulation_id}/power-rankings")
def simulation_power_rankings(
    simulation_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> list[dict]:
    run = _run_or_404(db, simulation_id, settings)
    if run.status != "completed":
        raise HTTPException(409, "Simulation is not completed")
    return power_rankings(db, run)


@router.get("/simulations/{simulation_id}/groups")
def simulation_groups(simulation_id: str, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> list[dict]:
    run = _run_or_404(db, simulation_id, settings)
    rows = db.scalars(select(SimulationGroupResult).where(SimulationGroupResult.simulation_id == simulation_id)
                      .order_by(SimulationGroupResult.group_id, SimulationGroupResult.occurrence_count.desc())).all()
    return [{"group_id": row.group_id, "order": [row.rank_1_team_id, row.rank_2_team_id, row.rank_3_team_id, row.rank_4_team_id],
             "count": row.occurrence_count, "probability": row.occurrence_count / max(run.progress_iterations, 1)} for row in rows]


@router.get("/simulations/{simulation_id}/bracket")
def simulation_bracket(simulation_id: str, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> list[dict]:
    run = _run_or_404(db, simulation_id, settings)
    rows = db.scalars(select(SimulationBracketResult).where(SimulationBracketResult.simulation_id == simulation_id)
                      .order_by(SimulationBracketResult.official_match_number, SimulationBracketResult.meeting_count.desc())).all()
    return [{"match_number": row.official_match_number, "team_a_id": row.team_a_id, "team_b_id": row.team_b_id,
             "meeting_count": row.meeting_count, "matchup_probability": row.meeting_count / max(run.progress_iterations, 1),
             "team_a_advance_probability": row.team_a_advance_count / max(row.meeting_count, 1)} for row in rows]


@router.post("/admin/squads/sync", dependencies=[Depends(require_admin)])
def sync_squads(db: Session = Depends(get_db), refresh_ea_cache: bool = False, skip_injuries: bool = False) -> dict:
    from world_cup_api.services.squad_sync import sync_squad_data

    report = sync_squad_data(db, refresh_ea_cache=refresh_ea_cache, fetch_injuries_enabled=not skip_injuries)
    return {
        "teams_processed": report.teams_processed,
        "players_written": report.players_written,
        "injuries_written": report.injuries_written,
        "sources": list(report.sources),
        "warnings": list(report.warnings),
    }


@router.post("/admin/markets/sync", dependencies=[Depends(require_admin)])
def sync_markets(db: Session = Depends(get_db), match_number: int | None = None) -> dict:
    numbers = [match_number] if match_number is not None else None
    reports = sync_upcoming_markets(db, match_numbers=numbers)
    champion_report = sync_wc_champion_markets(db)
    return {
        "fixtures": [
            {"match_id": report.match_id, "match_number": report.match_number, "queries": list(report.queries),
             "attena_hits": report.attena_hits, "stored_rows": report.stored_rows, "platforms": list(report.platforms),
             "warnings": list(report.warnings)}
            for report in reports
        ],
        "wc_winner": {
            "teams_matched": champion_report.teams_matched,
            "stored_rows": champion_report.stored_rows,
            "platforms": list(champion_report.platforms),
            "top_favorites": [{"fifa_code": code, "probability": prob} for code, prob in champion_report.top_favorites],
            "warnings": list(champion_report.warnings),
        },
    }


@router.post("/admin/tournament/refresh", dependencies=[Depends(require_admin)])
def refresh_tournament(db: Session = Depends(get_db), regenerate_seed_files: bool = True) -> dict:
    report = refresh_tournament_data(db, regenerate_seed_files=regenerate_seed_files)
    return {"fetched": report.fetched, "applied": report.applied, "skipped": report.skipped,
            "seed_regenerated": report.seed_regenerated, "warnings": list(report.warnings)}


@router.put("/admin/matches/{match_id}/result", dependencies=[Depends(require_admin)])
def put_result(match_id: int, payload: ResultInput, db: Session = Depends(get_db)) -> dict:
    data = payload.model_dump(exclude_none=False)
    if data["source_updated_at"] is None:
        data.pop("source_updated_at")
    try:
        result = revise_result(db, match_id, data)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"id": result.id, "match_id": result.match_id, "revision": result.revision}


@router.delete("/admin/matches/{match_id}/result", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_admin)])
def delete_result(match_id: int, db: Session = Depends(get_db)) -> Response:
    try:
        remove_current_result(db, match_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    return Response(status_code=204)


@router.get("/admin/matches/{match_id}/report-data", dependencies=[Depends(require_admin)])
def match_report_data(
    match_id: int,
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> dict:
    document = db.scalar(
        select(MatchReportDocument)
        .where(MatchReportDocument.match_id == match_id)
        .order_by(MatchReportDocument.created_at.desc())
        .limit(1)
    )
    if not document:
        raise HTTPException(404, "Match report not found for match")
    run = db.scalar(
        select(MatchReportExtractionRun)
        .where(MatchReportExtractionRun.document_id == document.id, MatchReportExtractionRun.is_active.is_(True))
        .order_by(MatchReportExtractionRun.created_at.desc())
        .limit(1)
    )
    if not run:
        raise HTTPException(404, "Active report extraction run not found")
    pages = db.scalars(
        select(MatchReportPage)
        .where(MatchReportPage.run_id == run.id)
        .order_by(MatchReportPage.page_number)
    ).all()
    page_ids = [page.id for page in pages]
    payload_rows = []
    if page_ids:
        from world_cup_api.db.report_models import MatchReportPagePayload

        payload_rows = db.scalars(
            select(MatchReportPagePayload).where(MatchReportPagePayload.page_id.in_(page_ids))
        ).all()
    payloads_by_page: dict[int, list[dict]] = {}
    for payload in payload_rows:
        payloads_by_page.setdefault(payload.page_id, []).append(
            {
                "type": payload.payload_type,
                "element_count": payload.element_count,
                "mapped_count": payload.mapped_count,
                "decorative_count": payload.decorative_count,
                "unresolved_count": payload.unresolved_count,
                "checksum": payload.checksum,
            }
        )
    return {
        "match_id": match_id,
        "document": {
            "id": document.id,
            "filename": document.filename,
            "sha256": document.sha256,
            "official_match_number": document.official_match_number,
            "status": document.status,
            "page_count": document.page_count,
            "template_key": document.template_key,
            "template_version": document.template_version,
            "created_at": document.created_at,
            "updated_at": document.updated_at,
        },
        "run": {
            "id": run.id,
            "status": run.status,
            "pipeline_version": run.pipeline_version,
            "template_version": run.template_version,
            "attempt": run.attempt,
            "quality_score": run.quality_score,
            "coverage": run.coverage,
            "artifact_root": run.artifact_root,
            "stats": run.stats_json,
            "errors": run.error_json or [],
            "created_at": run.created_at,
            "completed_at": run.completed_at,
        },
        "pages": [
            {
                "id": page.id,
                "page_number": page.page_number,
                "page_type": page.page_type,
                "section": page.section,
                "team_scope": page.team_scope,
                "team_id": page.team_id,
                "width_points": page.width_points,
                "height_points": page.height_points,
                "rotation": page.rotation,
                "render_uri": page.render_uri,
                "classification_confidence": page.classification_confidence,
                "raw_element_count": page.raw_element_count,
                "payloads": payloads_by_page.get(page.id, []),
            }
            for page in pages
        ],
        "participants": [_participant_payload(row) for row in _limited_rows(db, MatchReportParticipant, run.id, limit)],
        "observations": [_observation_payload(row) for row in _limited_rows(db, MatchReportObservation, run.id, limit)],
        "events": [_event_payload(row) for row in _limited_rows(db, MatchReportEvent, run.id, limit)],
        "spatial_features": [_spatial_feature_payload(row) for row in _limited_rows(db, MatchReportSpatialFeature, run.id, limit)],
        "network_edges": [_network_edge_payload(row) for row in _limited_rows(db, MatchReportNetworkEdge, run.id, limit)],
        "timeseries_points": [_timeseries_point_payload(row) for row in _limited_rows(db, MatchReportTimeseriesPoint, run.id, limit)],
        "issues": [_issue_payload(row) for row in _limited_rows(db, MatchReportIssue, run.id, limit)],
        "limit": limit,
    }


@router.post("/admin/imports/{dataset}/preview", dependencies=[Depends(require_admin)])
async def import_preview(dataset: str, file: UploadFile = File(...), source: str = Form("manual-csv"),
                         db: Session = Depends(get_db)) -> dict:
    try:
        run, rows, errors = preview_import(db, dataset, await file.read(), source)
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"id": run.id, "dataset_type": run.dataset_type, "status": run.status, "checksum": run.checksum,
            "record_count": run.record_count, "preview": rows, "errors": errors}


@router.post("/admin/imports/{run_id}/commit", dependencies=[Depends(require_admin)])
def import_commit(run_id: str, db: Session = Depends(get_db)) -> dict:
    try:
        run = commit_import(db, run_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"id": run.id, "status": run.status, "record_count": run.record_count}


@router.get("/admin/imports", dependencies=[Depends(require_admin)])
def import_history(db: Session = Depends(get_db)) -> list[dict]:
    runs = db.scalars(select(IngestionRun).order_by(IngestionRun.started_at.desc()).limit(100)).all()
    return [{"id": run.id, "dataset_type": run.dataset_type, "source": run.source, "status": run.status,
             "record_count": run.record_count, "error_count": run.error_count,
             "started_at": run.started_at, "completed_at": run.completed_at} for run in runs]


@router.get("/admin/data-freshness", dependencies=[Depends(require_admin)])
def data_freshness(db: Session = Depends(get_db)) -> list[dict]:
    datasets = db.scalars(select(IngestionRun.dataset_type).distinct()).all()
    output = []
    for dataset in datasets:
        latest = db.scalar(select(IngestionRun).where(IngestionRun.dataset_type == dataset,
                                                       IngestionRun.status == "committed")
                           .order_by(IngestionRun.completed_at.desc()).limit(1))
        output.append({"dataset_type": dataset, "fresh_at": latest.source_cutoff_at if latest else None,
                       "status": latest.status if latest else "never_imported"})
    return output


def _limited_rows(db: Session, model, run_id: str, limit: int) -> list:
    return db.scalars(select(model).where(model.run_id == run_id).order_by(model.id).limit(limit)).all()


def _participant_payload(row: MatchReportParticipant) -> dict:
    return {
        "id": row.id,
        "page_id": row.page_id,
        "team_id": row.team_id,
        "squad_player_id": row.squad_player_id,
        "team_source_name": row.team_source_name,
        "source_name": row.source_name,
        "normalized_name": row.normalized_name,
        "shirt_number": row.shirt_number,
        "position": row.position,
        "formation_role": row.formation_role,
        "is_starter": row.is_starter,
        "is_substitute": row.is_substitute,
        "is_captain": row.is_captain,
        "source_bbox": row.source_bbox_json,
        "source_element_ids": row.source_element_ids_json,
        "method": row.method,
        "confidence": row.confidence,
    }


def _observation_payload(row: MatchReportObservation) -> dict:
    return {
        "id": row.id,
        "page_id": row.page_id,
        "scope": row.scope,
        "team_id": row.team_id,
        "participant_id": row.participant_id,
        "metric_key": row.metric_key,
        "value_numeric": row.value_numeric,
        "value_text": row.value_text,
        "unit": row.unit,
        "period": row.period,
        "phase": row.phase,
        "dimensions": row.dimensions_json,
        "is_explicit_zero": row.is_explicit_zero,
        "is_blank": row.is_blank,
        "source_bbox": row.source_bbox_json,
        "source_element_ids": row.source_element_ids_json,
        "method": row.method,
        "confidence": row.confidence,
    }


def _event_payload(row: MatchReportEvent) -> dict:
    return {
        "id": row.id,
        "page_id": row.page_id,
        "team_id": row.team_id,
        "participant_id": row.participant_id,
        "event_type": row.event_type,
        "event_number": row.event_number,
        "minute": row.minute,
        "added_time": row.added_time,
        "match_second": row.match_second,
        "period": row.period,
        "category": row.category,
        "outcome": row.outcome,
        "body_part": row.body_part,
        "raw_start": [row.raw_start_x, row.raw_start_y],
        "raw_end": [row.raw_end_x, row.raw_end_y],
        "normalized_start": [row.norm_start_x, row.norm_start_y],
        "normalized_end": [row.norm_end_x, row.norm_end_y],
        "pitch_start_m": [row.pitch_start_x_m, row.pitch_start_y_m],
        "pitch_end_m": [row.pitch_end_x_m, row.pitch_end_y_m],
        "coordinate_space": row.coordinate_space,
        "attacking_direction": row.attacking_direction,
        "length_m": row.length_m,
        "angle_degrees": row.angle_degrees,
        "attributes": row.attributes_json,
        "source_bbox": row.source_bbox_json,
        "source_element_ids": row.source_element_ids_json,
        "method": row.method,
        "confidence": row.confidence,
    }


def _spatial_feature_payload(row: MatchReportSpatialFeature) -> dict:
    return {
        "id": row.id,
        "page_id": row.page_id,
        "team_id": row.team_id,
        "participant_id": row.participant_id,
        "feature_type": row.feature_type,
        "geometry_type": row.geometry_type,
        "coordinate_space": row.coordinate_space,
        "raw_geometry": row.raw_geometry_json,
        "normalized_geometry": row.normalized_geometry_json,
        "canonical_geometry": row.canonical_geometry_json,
        "category": row.category,
        "phase": row.phase,
        "value_numeric": row.value_numeric,
        "unit": row.unit,
        "attributes": row.attributes_json,
        "source_element_ids": row.source_element_ids_json,
        "method": row.method,
        "confidence": row.confidence,
    }


def _network_edge_payload(row: MatchReportNetworkEdge) -> dict:
    return {
        "id": row.id,
        "page_id": row.page_id,
        "team_id": row.team_id,
        "source_participant_id": row.source_participant_id,
        "target_participant_id": row.target_participant_id,
        "source_player_name": row.source_player_name,
        "target_player_name": row.target_player_name,
        "pass_count": row.pass_count,
        "pass_share": row.pass_share,
        "attributes": row.attributes_json,
        "source_bbox": row.source_bbox_json,
        "source_element_ids": row.source_element_ids_json,
        "method": row.method,
        "confidence": row.confidence,
    }


def _timeseries_point_payload(row: MatchReportTimeseriesPoint) -> dict:
    return {
        "id": row.id,
        "page_id": row.page_id,
        "team_id": row.team_id,
        "participant_id": row.participant_id,
        "team_source_name": row.team_source_name,
        "series_key": row.series_key,
        "period": row.period,
        "minute": row.minute,
        "match_second": row.match_second,
        "value": row.value,
        "unit": row.unit,
        "raw": [row.raw_x, row.raw_y],
        "attributes": row.attributes_json,
        "source_element_ids": row.source_element_ids_json,
        "method": row.method,
        "confidence": row.confidence,
    }


def _issue_payload(row: MatchReportIssue) -> dict:
    return {
        "id": row.id,
        "page_id": row.page_id,
        "severity": row.severity,
        "code": row.code,
        "message": row.message,
        "artifact_type": row.artifact_type,
        "source_bbox": row.source_bbox_json,
        "source_element_ids": row.source_element_ids_json,
        "evidence": row.evidence_json,
        "is_resolved": row.is_resolved,
        "resolution_note": row.resolution_note,
        "created_at": row.created_at,
    }


def _match_prediction_payload(match, forecast, sources: list[dict], has_external_market: bool) -> dict:
    return {"match_id": match.id, "generated_at": datetime.now(timezone.utc), "model_version": "nbinom-fused-strength-v1",
            "lambda_a": forecast.lambda_a, "lambda_b": forecast.lambda_b,
            "market": _triple(forecast.market), "model": _triple(forecast.model), "final": _triple(forecast.final),
            "score_distribution": forecast.score_matrix, "market_sources": sources,
            "data_quality": "market_blend" if has_external_market else "model_only"}


def _standing_dict(row) -> dict:
    return {"position": row.position, "team_id": row.team_id, "name": row.name, "played": row.played,
            "won": row.won, "drawn": row.drawn, "lost": row.lost, "goals_for": row.goals_for,
            "goals_against": row.goals_against, "goal_difference": row.goal_difference,
            "points": row.points, "conduct_score": row.conduct_score}


def _triple(values) -> dict | None:
    return {"team_a": values[0], "draw": values[1], "team_b": values[2]} if values else None


def _simulation_status(db: Session, run: Simulation) -> SimulationStatus:
    payload = SimulationStatus.model_validate(run).model_dump()
    payload["result_coverage"] = compute_result_coverage(db, run).to_dict()
    return SimulationStatus.model_validate(payload)


def _run_or_404(db: Session, simulation_id: str, settings: Settings) -> Simulation:
    if settings.published_simulation_id and simulation_id != settings.published_simulation_id:
        raise HTTPException(404, "Simulation not found")
    run = db.get(Simulation, simulation_id)
    if not run:
        raise HTTPException(404, "Simulation not found")
    return run


def _team_probability(row: SimulationTeamResult, run: Simulation) -> dict:
    n = max(run.progress_iterations, 1)
    return {"team_id": row.team_id, "win_group": row.finish_1_count / n,
            "finish_1": row.finish_1_count / n, "finish_2": row.finish_2_count / n,
            "finish_3": row.finish_3_count / n, "finish_4": row.finish_4_count / n,
            "top_two": (row.finish_1_count + row.finish_2_count) / n,
            "advance_as_third": row.advance_as_third_count / n, "round_of_32": row.round_of_32_count / n,
            "round_of_16": row.round_of_16_count / n, "quarterfinal": row.quarterfinal_count / n,
            "semifinal": row.semifinal_count / n, "final": row.final_count / n,
            "champion": row.champion_count / n, "eliminated": 1 - row.round_of_32_count / n,
            "expected_group_points": row.sum_group_points / n,
            "expected_group_goals_for": row.sum_group_goals_for / n,
            "expected_group_goals_against": row.sum_group_goals_against / n}


def _team_r32_rivals(
    db: Session,
    simulation_id: str,
    team_id: int,
    row: SimulationTeamResult,
    *,
    limit: int = 5,
) -> dict[str, list[dict]]:
    rivals = db.scalars(select(SimulationTeamR32Rival).where(
        SimulationTeamR32Rival.simulation_id == simulation_id,
        SimulationTeamR32Rival.team_id == team_id,
    ).order_by(
        SimulationTeamR32Rival.finish_position,
        SimulationTeamR32Rival.meeting_count.desc(),
    )).all()
    if not rivals:
        return {"as_winner": [], "as_runner_up": [], "as_third": []}

    opponent_ids = {rival.opponent_team_id for rival in rivals}
    opponents = {
        team.id: team
        for team in db.scalars(select(Team).where(Team.id.in_(opponent_ids))).all()
    }
    denominators = {
        1: max(row.finish_1_count, 1),
        2: max(row.finish_2_count, 1),
        3: max(row.finish_3_count, 1),
    }
    labels = {1: "as_winner", 2: "as_runner_up", 3: "as_third"}
    grouped: dict[str, list[dict]] = {label: [] for label in labels.values()}

    for position, label in labels.items():
        position_rows = sorted(
            (rival for rival in rivals if rival.finish_position == position),
            key=lambda rival: rival.meeting_count,
            reverse=True,
        )
        for rival in position_rows[:limit]:
            opponent = opponents.get(rival.opponent_team_id)
            if opponent is None:
                continue
            grouped[label].append({
                "team_id": opponent.id,
                "name": opponent.name,
                "fifa_code": opponent.fifa_code,
                "probability": rival.meeting_count / denominators[position],
            })
    return grouped
