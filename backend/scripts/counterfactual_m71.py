#!/usr/bin/env python3
"""One-off counterfactual: lock M71 (COL vs POR) and measure ARG-POR in M100."""
from __future__ import annotations

import copy
from collections import defaultdict

from sqlalchemy import select

from world_cup_api.db.models import Team
from world_cup_api.db.session import SessionLocal
from world_cup_api.simulation.engine import build_input_snapshot, run_trials

ARG, POR = 37, 41
ITER = 100_000
SEED = 9876


def m100_arg_por(result: dict) -> float:
    total = 0
    for (num, a, b), counts in result["bracket"].items():
        if num == 100 and {a, b} == {ARG, POR}:
            total += counts["meetings"]
    return total / result["completed"]


def lock_match(snapshot: dict, match_number: int, goals_a: int, goals_b: int) -> dict:
    locked_snapshot = copy.deepcopy(snapshot)
    for group in locked_snapshot["groups"].values():
        for match in group["matches"]:
            if match["official_match_number"] == match_number:
                match["completed"] = [goals_a, goals_b, 0, 0, 0, 0]
    locked = set(locked_snapshot.get("locked_match_numbers") or [])
    locked.add(match_number)
    locked_snapshot["locked_match_numbers"] = sorted(locked)
    return locked_snapshot


def top_arg_m100_opponents(result: dict, names: dict[int, str], limit: int = 6) -> list[tuple[str, float]]:
    counts: dict[int, int] = defaultdict(int)
    for (num, a, b), row in result["bracket"].items():
        if num != 100:
            continue
        if a == ARG:
            counts[b] += row["meetings"]
        elif b == ARG:
            counts[a] += row["meetings"]
    ranked = sorted(counts.items(), key=lambda item: -item[1])[:limit]
    return [(names.get(team_id, str(team_id)), count / ITER) for team_id, count in ranked]


def main() -> None:
    with SessionLocal() as db:
        base, _ = build_input_snapshot(db)
        names = {team.id: team.name for team in db.scalars(select(Team)).all()}

    baseline = run_trials(base, ITER, SEED)
    por_win = run_trials(lock_match(base, 71, 0, 1), ITER, SEED)
    por_win_alt = run_trials(lock_match(base, 71, 1, 2), ITER, SEED)

    p0 = m100_arg_por(baseline)
    p1 = m100_arg_por(por_win)
    p2 = m100_arg_por(por_win_alt)

    print(f"Baseline (M71 open):        {p0 * 100:.2f}%")
    print(f"COL 0-1 POR at M71:         {p1 * 100:.2f}%  (delta {(p1 - p0) * 100:+.2f} pp)")
    print(f"COL 1-2 POR at M71:         {p2 * 100:.2f}%  (delta {(p2 - p0) * 100:+.2f} pp)")
    print("\nTop ARG M100 opponents if COL 0-1 POR:")
    for label, prob in top_arg_m100_opponents(por_win, names):
        print(f"  {label}: {prob * 100:.2f}%")


if __name__ == "__main__":
    main()
