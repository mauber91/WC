from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from world_cup_api.db.models import Group, Simulation, SimulationTeamResult, Team, TournamentTeam
from world_cup_api.domain.teams import team_slug
from world_cup_api.domain.team_strength import fuse_strength
from world_cup_api.modeling.context_params import DEFAULT_CONTEXT_PARAMS
from world_cup_api.services.champion_market_sync import champion_probs_by_team_id
from world_cup_api.services.tournament_elo import current_tournament_elos


def tournament_power_score(probs: dict[str, float]) -> float:
    """Weighted reach through the knockout rounds (0–100 scale for a dominant favorite)."""
    return (
        probs["champion"] * 100
        + probs["final"] * 60
        + probs["semifinal"] * 35
        + probs["quarterfinal"] * 20
        + probs["round_of_16"] * 10
        + probs["round_of_32"] * 5
    )


def blend_power_score(
    sim_probs: dict[str, float],
    market_prob: float | None,
    *,
    market_blend: float,
    max_market_prob: float,
) -> float:
    """Blend simulation knockout reach with normalized WC-winner market prices."""
    sim_score = tournament_power_score(sim_probs)
    if market_blend <= 0 or market_prob is None or max_market_prob <= 0:
        return sim_score
    market_score = (market_prob / max_market_prob) * 100.0
    return (1.0 - market_blend) * sim_score + market_blend * market_score


def _team_probabilities(row: SimulationTeamResult, iterations: int) -> dict[str, float]:
    n = max(iterations, 1)
    return {
        "win_group": row.finish_1_count / n,
        "top_two": (row.finish_1_count + row.finish_2_count) / n,
        "round_of_32": row.round_of_32_count / n,
        "round_of_16": row.round_of_16_count / n,
        "quarterfinal": row.quarterfinal_count / n,
        "semifinal": row.semifinal_count / n,
        "final": row.final_count / n,
        "champion": row.champion_count / n,
    }


def power_rankings(db: Session, simulation: Simulation) -> list[dict]:
    iterations = simulation.progress_iterations
    params = DEFAULT_CONTEXT_PARAMS
    elo_table = current_tournament_elos(db, simulation.tournament_id)
    champion_probs = champion_probs_by_team_id(db)

    memberships = {
        row.team_id: row
        for row in db.scalars(
            select(TournamentTeam).where(TournamentTeam.tournament_id == simulation.tournament_id),
        ).all()
    }
    groups = {group.id: group.code for group in db.scalars(select(Group)).all()}

    from world_cup_api.services.predictions import _latest_fifa_ranks

    team_ids = set(elo_table)
    fifa_ranks = _latest_fifa_ranks(db, team_ids, 50.0)

    rows = db.execute(
        select(SimulationTeamResult, Team)
        .join(Team, Team.id == SimulationTeamResult.team_id)
        .where(SimulationTeamResult.simulation_id == simulation.id),
    ).all()

    market_probs = [champion_probs.get(team.id) for _, team in rows if champion_probs.get(team.id)]
    max_market_prob = max(market_probs) if market_probs else 0.0

    ranked: list[dict] = []
    for sim_row, team in rows:
        membership = memberships.get(team.id)
        group_code = groups.get(membership.group_id) if membership else None
        probs = _team_probabilities(sim_row, iterations)
        sim_index = tournament_power_score(probs)
        market_prob = champion_probs.get(team.id)
        fused = fuse_strength(
            elo_table[team.id],
            fifa_ranks.get(team.id, 50.0),
            fifa_weight=params.fifa_strength_weight,
            champion_prob=champion_probs.get(team.id),
            champion_weight=params.champion_strength_weight,
            champion_field_size=params.champion_field_size,
        )
        ranked.append({
            "team_id": team.id,
            "slug": team_slug(team.name),
            "fifa_code": team.fifa_code,
            "name": team.name,
            "group_code": group_code,
            "is_host": bool(membership and membership.is_host),
            "fifa_rank": int(fifa_ranks.get(team.id, 50)),
            "tournament_elo": round(elo_table[team.id]),
            "fused_strength": round(fused),
            "sim_power_score": round(sim_index, 2),
            "market_power_score": round(
                (market_prob / max_market_prob) * 100.0, 2,
            ) if market_prob is not None and max_market_prob > 0 else None,
            "power_score": round(
                blend_power_score(
                    probs,
                    market_prob,
                    market_blend=params.power_rank_market_blend,
                    max_market_prob=max_market_prob,
                ),
                2,
            ),
            **probs,
        })

    ranked.sort(
        key=lambda row: (-row["power_score"], -row["champion"], -row["fused_strength"], row["name"]),
    )
    for index, row in enumerate(ranked, start=1):
        row["rank"] = index
    return ranked
