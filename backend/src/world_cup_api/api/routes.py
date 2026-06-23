from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from world_cup_api.api.dependencies import require_admin
from world_cup_api.api.schemas import ResultInput, SimulationInput, SimulationStatus
from world_cup_api.config import Settings, get_settings
from world_cup_api.db.models import (
    BookmakerOdds, Group, PredictionMarketPrice, Simulation, SimulationBracketResult,
    SimulationGroupResult, SimulationTeamR32Rival, SimulationTeamResult, Team, TournamentTeam, IngestionRun,
)
from world_cup_api.db.session import get_db
from world_cup_api.jobs.scheduler import schedule_simulation
from world_cup_api.services.predictions import forecast_match
from world_cup_api.services.results import remove_current_result, revise_result
from world_cup_api.services.champion_market_sync import sync_wc_champion_markets
from world_cup_api.services.market_sync import sync_upcoming_markets
from world_cup_api.services.tournament_refresh import refresh_tournament_data
from world_cup_api.services.simulation_coverage import compute_result_coverage
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
    return {"match_id": match.id, "generated_at": datetime.now(timezone.utc), "model_version": "nbinom-fused-strength-v1",
            "lambda_a": forecast.lambda_a, "lambda_b": forecast.lambda_b,
            "market": _triple(forecast.market), "model": _triple(forecast.model), "final": _triple(forecast.final),
            "score_distribution": forecast.score_matrix, "market_sources": sources,
            "data_quality": "market_blend" if has_external_market else "model_only"}


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
