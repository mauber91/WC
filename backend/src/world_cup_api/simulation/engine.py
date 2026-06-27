from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Callable

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from world_cup_api.db.models import (
    Group, Match, MatchResult, Team, TeamRating, ThirdPlaceAssignment, Tournament, TournamentTeam,
)
from world_cup_api.domain.bracket import KNOCKOUT_FEEDERS, ROUND_32
from world_cup_api.domain.host_advantage import venue_home_flags
from world_cup_api.domain.knockout_fixtures import knockout_venues
from world_cup_api.domain.match_context import (
    group_match_context,
    knockout_rest_context,
    knockout_venue_coords,
    travel_km_for_team,
)
from world_cup_api.domain.group_situation import (
    analyze_group_before_matchday3,
    apply_collusion_draw_boost,
    md3_fixtures_from_matches,
    mutual_draw_incentive,
    should_rotate_team,
)
from world_cup_api.domain.standings import MatchRecord, StandingRow, calculate_group_table, rank_third_place
from world_cup_api.domain.team_strength import fuse_strength
from world_cup_api.domain.tournament_elo import build_elo_table
from world_cup_api.domain.venues import team_base_camps
from world_cup_api.modeling.context_params import DEFAULT_CONTEXT_PARAMS, elo_sigma
from world_cup_api.modeling.prediction import MatchForecast, build_forecast, knockout_winner
from world_cup_api.services.champion_market_sync import champion_probs_by_team_id
from world_cup_api.services.tournament_elo import baseline_elos, current_tournament_elos, team_elo


def _context_params_dict() -> dict[str, float | int]:
    params = DEFAULT_CONTEXT_PARAMS
    return {
        "beta_rest": params.beta_rest,
        "rest_cap_days": params.rest_cap_days,
        "beta_travel": params.beta_travel,
        "travel_ref_km": params.travel_ref_km,
        "elo_sigma_base": params.elo_sigma_base,
        "rotation_elo_penalty": params.rotation_elo_penalty,
        "rotation_elo_locked_first": params.rotation_elo_locked_first,
        "rotation_elo_clinched": params.rotation_elo_clinched,
        "rotation_elo_eliminated": params.rotation_elo_eliminated,
        "collusion_draw_boost": params.collusion_draw_boost,
        "goal_dispersion": params.goal_dispersion,
        "fifa_strength_weight": params.fifa_strength_weight,
        "champion_strength_weight": params.champion_strength_weight,
        "champion_field_size": params.champion_field_size,
        "market_blend_alpha": params.market_blend_alpha,
        "host_advantage_elo": params.host_advantage_elo,
        "clinch_points": params.clinch_points,
        "elim_points": params.elim_points,
    }


def _rotation_key(rot_a: bool, rot_b: bool) -> str:
    return f"{int(rot_a)}{int(rot_b)}"


from world_cup_api.services.tournament_elo import team_elo


def _build_forecast_matrix(
    db: Session,
    match: Match,
    *,
    elo_a: float | None = None,
    elo_b: float | None = None,
    context: dict[str, float] | None = None,
) -> tuple[float, float, tuple[tuple[float, ...], ...]]:
    from world_cup_api.services.predictions import _latest_fifa_rank, _market_consensus

    team_a = db.get(Team, match.team_a_id)
    team_b = db.get(Team, match.team_b_id)
    if team_a is None or team_b is None:
        raise LookupError("Match teams are not known")
    rating_a = elo_a if elo_a is not None else team_elo(db, match.tournament_id, match.team_a_id)
    rating_b = elo_b if elo_b is not None else team_elo(db, match.tournament_id, match.team_b_id)
    params = DEFAULT_CONTEXT_PARAMS
    champion_probs = champion_probs_by_team_id(db)
    rating_a = fuse_strength(
        rating_a,
        _latest_fifa_rank(db, match.team_a_id, 50),
        fifa_weight=params.fifa_strength_weight,
        champion_prob=champion_probs.get(match.team_a_id),
        champion_weight=params.champion_strength_weight,
        champion_field_size=params.champion_field_size,
    )
    rating_b = fuse_strength(
        rating_b,
        _latest_fifa_rank(db, match.team_b_id, 50),
        fifa_weight=params.fifa_strength_weight,
        champion_prob=champion_probs.get(match.team_b_id),
        champion_weight=params.champion_strength_weight,
        champion_field_size=params.champion_field_size,
    )
    market, _, has_external_market = _market_consensus(db, match.id)
    host_a, host_b = venue_home_flags(team_a.country_code, team_b.country_code, match.host_country)
    ctx = context or {}
    blend_alpha = params.market_blend_alpha if has_external_market else 0.0
    forecast = build_forecast(
        rating_a,
        rating_b,
        market,
        host_a,
        host_b,
        rest_a=ctx.get("rest_a", 0.0),
        rest_b=ctx.get("rest_b", 0.0),
        travel_a=ctx.get("travel_a", 0.0),
        travel_b=ctx.get("travel_b", 0.0),
        beta_rest=params.beta_rest,
        rest_cap=params.rest_cap_days,
        beta_travel=params.beta_travel,
        travel_ref=params.travel_ref_km,
        goal_dispersion=params.goal_dispersion,
        market_blend_alpha=blend_alpha,
        host_advantage=params.host_advantage_elo,
    )
    return forecast.lambda_a, forecast.lambda_b, forecast.score_matrix


def _snapshot_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _json_safe_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Return a copy safe for SQLAlchemy JSON columns."""
    payload = json.loads(json.dumps(snapshot, default=str, sort_keys=True))
    return payload


def build_input_snapshot(db: Session) -> tuple[dict, str]:
    tournament = db.scalar(select(Tournament).where(Tournament.code == "FWC2026"))
    if tournament is None:
        raise RuntimeError("Tournament seed data is missing")
    base_camps = team_base_camps()
    team_rows = db.execute(
        select(Team, TournamentTeam).join(TournamentTeam, TournamentTeam.team_id == Team.id)
        .where(TournamentTeam.tournament_id == tournament.id)
    ).all()
    teams: dict[str, dict] = {}
    base_elos = baseline_elos(db, tournament.id)
    live_elos = current_tournament_elos(db, tournament.id)
    champion_probs = champion_probs_by_team_id(db)
    fifa_by_id: dict[int, str] = {}
    for team, membership in team_rows:
        ratings = db.scalars(select(TeamRating).where(TeamRating.team_id == team.id).order_by(TeamRating.effective_at.desc())).all()
        ranks = [r.rank or int(r.rating_value) for r in ratings if r.rating_type == "FIFA_RANK"]
        camp = base_camps[team.fifa_code]
        fifa_by_id[team.id] = team.fifa_code
        teams[str(team.id)] = {
            "id": team.id,
            "fifa_code": team.fifa_code,
            "name": team.name,
            "country_code": team.country_code,
            "confederation": team.confederation,
            "elo_base": base_elos[team.id],
            "elo": live_elos[team.id],
            "ranks": ranks,
            "host": membership.is_host,
            "group_id": membership.group_id,
            "base_camp": [camp.lat, camp.lon],
            "elo_sigma": elo_sigma(team.confederation),
            "champion_prob": champion_probs.get(team.id),
        }

    raw_group_matches: dict[str, list[dict[str, Any]]] = {}
    groups: dict[str, dict] = {}
    locked_match_numbers: list[int] = []
    for group in db.scalars(select(Group).order_by(Group.sort_order)):
        group_teams = [value for value in teams.values() if value["group_id"] == group.id]
        group_matches: list[dict[str, Any]] = []
        for match in db.scalars(select(Match).where(Match.group_id == group.id).order_by(Match.scheduled_at)):
            current = db.scalar(select(MatchResult).where(MatchResult.match_id == match.id, MatchResult.is_current.is_(True)))
            item: dict[str, Any] = {
                "id": match.id,
                "official_match_number": match.official_match_number,
                "a": match.team_a_id,
                "b": match.team_b_id,
                "scheduled_at": match.scheduled_at,
                "venue": match.venue,
            }
            if current:
                item["completed"] = [
                    current.team_a_goals_90, current.team_b_goals_90,
                    current.conduct_a, current.conduct_b,
                    current.red_cards_a, current.red_cards_b,
                ]
                locked_match_numbers.append(match.official_match_number)
            group_matches.append(item)
        raw_group_matches[group.code] = group_matches
        context_by_match = group_match_context(group_matches, fifa_by_id)
        ordered = sorted(group_matches, key=lambda row: row["scheduled_at"])
        for index, item in enumerate(ordered):
            ctx = context_by_match[item["id"]]
            item["matchday"] = int(ctx["matchday"])
            item["context"] = ctx
            if "completed" not in item:
                if item["matchday"] == 3:
                    match_obj = db.get(Match, item["id"])
                    assert match_obj is not None
                    penalty = DEFAULT_CONTEXT_PARAMS.rotation_elo_locked_first
                    elo_a = live_elos[match_obj.team_a_id]
                    elo_b = live_elos[match_obj.team_b_id]
                    variants: dict[str, dict[str, Any]] = {}
                    for rot_a in (False, True):
                        for rot_b in (False, True):
                            adj_a = elo_a - (penalty if rot_a else 0.0)
                            adj_b = elo_b - (penalty if rot_b else 0.0)
                            lambda_a, lambda_b, matrix = _build_forecast_matrix(
                                db, match_obj, elo_a=adj_a, elo_b=adj_b, context=ctx,
                            )
                            variants[_rotation_key(rot_a, rot_b)] = {
                                "lambda_a": lambda_a,
                                "lambda_b": lambda_b,
                                "matrix": matrix,
                            }
                    item["rotation_variants"] = variants
                else:
                    match_obj = db.get(Match, item["id"])
                    assert match_obj is not None
                    lambda_a, lambda_b, matrix = _build_forecast_matrix(db, match_obj, context=ctx)
                    item["forecast"] = {"lambda_a": lambda_a, "lambda_b": lambda_b, "matrix": matrix}
        groups[group.code] = {"id": group.id, "teams": group_teams, "matches": ordered}

    assignments: dict[str, dict[str, str]] = defaultdict(dict)
    for row in db.scalars(select(ThirdPlaceAssignment).where(ThirdPlaceAssignment.ruleset_version == tournament.ruleset_version)):
        assignments[row.qualified_group_set][str(row.target_match_number)] = row.third_place_group_code

    knockout_rest = {str(k): list(v) for k, v in knockout_rest_context(raw_group_matches).items()}
    knockout_coords = {str(k): list(v) for k, v in knockout_venue_coords().items()}

    for group in groups.values():
        for item in group["matches"]:
            item["scheduled_at"] = _snapshot_datetime(item["scheduled_at"])

    snapshot = _json_safe_snapshot({
        "tournament_id": tournament.id,
        "ruleset_version": tournament.ruleset_version,
        "cutoff": datetime.now(timezone.utc).isoformat(),
        "locked_match_numbers": sorted(locked_match_numbers),
        "teams": teams,
        "groups": groups,
        "knockout_venues": knockout_venues(),
        "knockout_rest": knockout_rest,
        "knockout_venue_coords": knockout_coords,
        "context_params": _context_params_dict(),
        "third_place_assignments": assignments,
    })
    hash_payload = {key: value for key, value in snapshot.items() if key != "cutoff"}
    encoded = json.dumps(hash_payload, sort_keys=True, separators=(",", ":")).encode()
    return snapshot, hashlib.sha256(encoded).hexdigest()


def _group_standing_rows(group: dict) -> list[StandingRow]:
    return [
        StandingRow(team_id=team["id"], name=team["name"], fifa_rank_history=tuple(team["ranks"]))
        for team in group["teams"]
    ]


def _simulate_group_match(
    match: dict[str, Any],
    rng: np.random.Generator,
    *,
    rot_a: bool = False,
    rot_b: bool = False,
    draw_boost: float = 0.0,
) -> tuple[int, int, int, int]:
    if "completed" in match:
        goals_a, goals_b, conduct_a, conduct_b = match["completed"][:4]
        return goals_a, goals_b, conduct_a, conduct_b
    if "rotation_variants" in match:
        payload = match["rotation_variants"][_rotation_key(rot_a, rot_b)]
    else:
        payload = match["forecast"]
    matrix = np.asarray(payload["matrix"], dtype=float)
    if draw_boost > 0:
        matrix = apply_collusion_draw_boost(matrix, draw_boost)
    index = int(rng.choice(matrix.size, p=matrix.ravel()))
    goals_a, goals_b = divmod(index, matrix.shape[1])
    conduct_a, conduct_b = -int(rng.poisson(2.0)), -int(rng.poisson(2.0))
    return goals_a, goals_b, conduct_a, conduct_b


def run_trials(
    snapshot: dict,
    iterations: int,
    seed: int,
    progress: Callable[[int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> dict:
    rng = np.random.default_rng(seed)
    team_results: dict[int, Counter] = {int(team_id): Counter() for team_id in snapshot["teams"]}
    group_orders: Counter = Counter()
    bracket_results: dict[tuple[int, int, int], Counter] = defaultdict(Counter)
    r32_rivals: Counter = Counter()
    completed = 0
    params = snapshot.get("context_params", _context_params_dict())
    baseline = {
        int(team_id): float(team.get("elo_base", team["elo"]))
        for team_id, team in snapshot["teams"].items()
    }
    sigmas = {int(team_id): float(team["elo_sigma"]) for team_id, team in snapshot["teams"].items()}

    for trial in range(iterations):
        if trial % 1000 == 0 and cancelled and cancelled():
            break
        perturbed_baseline = {
            team_id: baseline[team_id] + rng.normal(0.0, sigmas[team_id])
            for team_id in baseline
        }

        group_rankings: dict[str, list[StandingRow]] = {}
        third_rows: list[StandingRow] = []
        group_stage_results: list[tuple[int, int, int, int]] = []

        for group_code, group in snapshot["groups"].items():
            records: list[MatchRecord] = []
            matches = sorted(group["matches"], key=lambda item: item["matchday"])
            early = [match for match in matches if match["matchday"] < 3]
            late = [match for match in matches if match["matchday"] == 3]

            for match in early:
                goals_a, goals_b, conduct_a, conduct_b = _simulate_group_match(match, rng)
                records.append(MatchRecord(match["a"], match["b"], goals_a, goals_b, conduct_a, conduct_b))
                group_stage_results.append((match["a"], match["b"], goals_a, goals_b))

            md3_fixtures = md3_fixtures_from_matches(group["matches"])
            situation = analyze_group_before_matchday3(_group_standing_rows(group), records, md3_fixtures)
            situations = situation.by_team_id()

            for match in late:
                team_a = situations[match["a"]]
                team_b = situations[match["b"]]
                rot_a = should_rotate_team(team_a, params)
                rot_b = should_rotate_team(team_b, params)
                draw_boost = float(params["collusion_draw_boost"]) if mutual_draw_incentive(team_a, team_b) else 0.0
                goals_a, goals_b, conduct_a, conduct_b = _simulate_group_match(
                    match, rng, rot_a=rot_a, rot_b=rot_b, draw_boost=draw_boost,
                )
                records.append(MatchRecord(match["a"], match["b"], goals_a, goals_b, conduct_a, conduct_b))
                group_stage_results.append((match["a"], match["b"], goals_a, goals_b))

            table = calculate_group_table(_group_standing_rows(group), records).rows
            group_rankings[group_code] = table
            third_rows.append(table[2])
            group_orders[(group["id"], *(row.team_id for row in table))] += 1
            for row in table:
                aggregate = team_results[row.team_id]
                aggregate[f"finish_{row.position}"] += 1
                aggregate["sum_points"] += row.points
                aggregate["sum_gf"] += row.goals_for
                aggregate["sum_ga"] += row.goals_against

        trial_elos = build_elo_table(perturbed_baseline, group_stage_results)
        forecast_cache: dict[tuple[Any, ...], MatchForecast] = {}

        ranked_thirds = rank_third_place(third_rows).rows
        qualifying_thirds = ranked_thirds[:8]
        qualified_group_set = "".join(sorted(_group_for_team(group_rankings, row.team_id) for row in qualifying_thirds))
        third_by_group = {_group_for_team(group_rankings, row.team_id): row.team_id for row in qualifying_thirds}
        assignment = snapshot["third_place_assignments"][qualified_group_set]
        winners: dict[int, int] = {}
        losers: dict[int, int] = {}
        for match_number, sources in ROUND_32.items():
            team_a = _resolve_source(sources[0], group_rankings, assignment, third_by_group)
            team_b = _resolve_source(sources[1], group_rankings, assignment, third_by_group)
            team_results[team_a]["round_of_32"] += 1
            team_results[team_b]["round_of_32"] += 1
            if sources[0][0] == "third":
                team_results[team_a]["advance_as_third"] += 1
            if sources[1][0] == "third":
                team_results[team_b]["advance_as_third"] += 1
            _record_r32_rivals(r32_rivals, group_rankings, team_a, team_b)
            winner = _play_knockout(team_a, team_b, match_number, snapshot, rng, forecast_cache, trial_elos, params)
            winners[match_number] = winner
            losers[match_number] = team_b if winner == team_a else team_a
            bracket_results[(match_number, team_a, team_b)]["meetings"] += 1
            bracket_results[(match_number, team_a, team_b)]["a_wins"] += int(winner == team_a)
            team_results[winner]["round_of_16"] += 1

        for match_number in range(89, 105):
            if match_number == 103:
                continue
            feeders = KNOCKOUT_FEEDERS.get(match_number)
            if feeders is None:
                continue
            team_a, team_b = winners[feeders[0]], winners[feeders[1]]
            winner = _play_knockout(team_a, team_b, match_number, snapshot, rng, forecast_cache, trial_elos, params)
            winners[match_number] = winner
            losers[match_number] = team_b if winner == team_a else team_a
            bracket_results[(match_number, team_a, team_b)]["meetings"] += 1
            bracket_results[(match_number, team_a, team_b)]["a_wins"] += int(winner == team_a)
            stage = {89: "quarterfinal", 97: "semifinal", 101: "final", 104: "champion"}
            threshold = max(key for key in stage if match_number >= key)
            team_results[winner][stage[threshold]] += 1
        bronze_a, bronze_b = losers[101], losers[102]
        bronze_winner = _play_knockout(bronze_a, bronze_b, 103, snapshot, rng, forecast_cache, trial_elos, params)
        bracket_results[(103, bronze_a, bronze_b)]["meetings"] += 1
        bracket_results[(103, bronze_a, bronze_b)]["a_wins"] += int(bronze_winner == bronze_a)
        completed += 1
        if progress and (completed % 1000 == 0 or completed == iterations):
            progress(completed)
    return {
        "completed": completed,
        "teams": team_results,
        "groups": group_orders,
        "bracket": bracket_results,
        "r32_rivals": r32_rivals,
    }


def run_trials_parallel(
    snapshot: dict,
    iterations: int,
    seed: int,
    max_workers: int = 2,
    progress: Callable[[int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> dict:
    """Run fixed deterministic subchunks; scheduling order and worker count do not alter results."""
    chunk_size = 2_500
    chunks = [(index, min(chunk_size, iterations - start)) for index, start in enumerate(range(0, iterations, chunk_size))]
    aggregate = {
        "completed": 0,
        "teams": {int(team_id): Counter() for team_id in snapshot["teams"]},
        "groups": Counter(),
        "bracket": defaultdict(Counter),
        "r32_rivals": Counter(),
    }
    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(run_trials, snapshot, count, _child_seed(seed, index)): index
            for index, count in chunks
        }
        for future in as_completed(futures):
            if cancelled and cancelled():
                for pending in futures:
                    pending.cancel()
                break
            result = future.result()
            aggregate["completed"] += result["completed"]
            for team_id, counts in result["teams"].items():
                aggregate["teams"][team_id].update(counts)
            aggregate["groups"].update(result["groups"])
            for key, counts in result["bracket"].items():
                aggregate["bracket"][key].update(counts)
            aggregate["r32_rivals"].update(result["r32_rivals"])
            if progress:
                progress(aggregate["completed"])
    return aggregate


def _child_seed(root_seed: int, chunk_index: int) -> int:
    return int(np.random.SeedSequence([root_seed, chunk_index]).generate_state(1, dtype=np.uint64)[0])


def _group_for_team(rankings: dict[str, list[StandingRow]], team_id: int) -> str:
    return next(code for code, rows in rankings.items() if any(row.team_id == team_id for row in rows))


def _position_for_team(rankings: dict[str, list[StandingRow]], team_id: int) -> int:
    group_code = _group_for_team(rankings, team_id)
    for index, row in enumerate(rankings[group_code]):
        if row.team_id == team_id:
            return index + 1
    raise ValueError(f"Team {team_id} not found in group rankings")


def _record_r32_rivals(
    rivals: Counter,
    rankings: dict[str, list[StandingRow]],
    team_a: int,
    team_b: int,
) -> None:
    for team_id, opponent_id in ((team_a, team_b), (team_b, team_a)):
        position = _position_for_team(rankings, team_id)
        if position > 3:
            continue
        rivals[(team_id, position, opponent_id)] += 1


def _resolve_source(source: tuple[str, str], rankings: dict[str, list[StandingRow]], assignment: dict[str, str], thirds: dict[str, int]) -> int:
    kind, reference = source
    if kind == "winner":
        return rankings[reference][0].team_id
    if kind == "runner":
        return rankings[reference][1].team_id
    return thirds[assignment[reference]]


def _play_knockout(
    team_a: int,
    team_b: int,
    match_number: int,
    snapshot: dict,
    rng: np.random.Generator,
    cache: dict[tuple[Any, ...], MatchForecast],
    elos: dict[int, float],
    params: dict[str, float | int],
) -> int:
    a, b = snapshot["teams"][str(team_a)], snapshot["teams"][str(team_b)]
    host_country = snapshot.get("knockout_venues", {}).get(str(match_number), snapshot.get("knockout_venues", {}).get(match_number))
    host_a, host_b = venue_home_flags(a["country_code"], b["country_code"], host_country)
    rest_a, rest_b = snapshot["knockout_rest"].get(str(match_number), snapshot["knockout_rest"].get(match_number, (0.0, 0.0)))
    venue_coords = snapshot["knockout_venue_coords"].get(str(match_number), snapshot["knockout_venue_coords"].get(match_number))
    travel_a = travel_km_for_team(tuple(a["base_camp"]), tuple(venue_coords)) if venue_coords else 0.0
    travel_b = travel_km_for_team(tuple(b["base_camp"]), tuple(venue_coords)) if venue_coords else 0.0
    rating_a = int(round(elos[team_a]))
    rating_b = int(round(elos[team_b]))
    key = (
        team_a, team_b, rating_a, rating_b, host_a, host_b,
        round(rest_a, 2), round(rest_b, 2), round(travel_a), round(travel_b),
    )
    if key not in cache:
        fifa_w = float(params.get("fifa_strength_weight", DEFAULT_CONTEXT_PARAMS.fifa_strength_weight))
        champ_w = float(params.get("champion_strength_weight", DEFAULT_CONTEXT_PARAMS.champion_strength_weight))
        field_size = int(params.get("champion_field_size", DEFAULT_CONTEXT_PARAMS.champion_field_size))
        strength_a = fuse_strength(
            elos[team_a],
            a["ranks"][0],
            fifa_weight=fifa_w,
            champion_prob=a.get("champion_prob"),
            champion_weight=champ_w,
            champion_field_size=field_size,
        )
        strength_b = fuse_strength(
            elos[team_b],
            b["ranks"][0],
            fifa_weight=fifa_w,
            champion_prob=b.get("champion_prob"),
            champion_weight=champ_w,
            champion_field_size=field_size,
        )
        cache[key] = build_forecast(
            strength_a,
            strength_b,
            host_a=host_a,
            host_b=host_b,
            rest_a=rest_a,
            rest_b=rest_b,
            travel_a=travel_a,
            travel_b=travel_b,
            beta_rest=float(params["beta_rest"]),
            rest_cap=float(params["rest_cap_days"]),
            beta_travel=float(params["beta_travel"]),
            travel_ref=float(params["travel_ref_km"]),
            goal_dispersion=float(params.get("goal_dispersion", DEFAULT_CONTEXT_PARAMS.goal_dispersion)),
            market_blend_alpha=0.0,
            host_advantage=float(params.get("host_advantage_elo", DEFAULT_CONTEXT_PARAMS.host_advantage_elo)),
        )
    return knockout_winner(team_a, team_b, cache[key], rng)
