from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from world_cup_api.config import ROOT_DIR
from world_cup_api.db.models import Match, MatchResult, Team
from world_cup_api.ingestion.fifa import FifaGroupResult, fetch_finished_group_results
from world_cup_api.services.results import revise_result


@dataclass(frozen=True)
class TournamentRefreshReport:
    fetched: int
    applied: int
    skipped: int
    warnings: tuple[str, ...]
    seed_regenerated: bool


def refresh_tournament_data(db: Session, *, regenerate_seed_files: bool = True) -> TournamentRefreshReport:
    warnings: list[str] = []
    try:
        finished = fetch_finished_group_results()
    except RuntimeError as exc:
        warnings.append(str(exc))
        return TournamentRefreshReport(0, 0, 0, tuple(warnings), False)

    applied = 0
    skipped = 0
    for item in finished:
        outcome = _apply_result(db, item, warnings)
        if outcome == "applied":
            applied += 1
        else:
            skipped += 1

    seed_regenerated = False
    if regenerate_seed_files and finished:
        try:
            regenerate_seed_csvs()
            seed_regenerated = True
        except RuntimeError as exc:
            warnings.append(str(exc))

    db.commit()
    return TournamentRefreshReport(
        fetched=len(finished),
        applied=applied,
        skipped=skipped,
        warnings=tuple(warnings),
        seed_regenerated=seed_regenerated,
    )


def regenerate_seed_csvs() -> None:
    script = ROOT_DIR / "scripts" / "build_official_seed.py"
    if not script.exists():
        raise RuntimeError(f"Seed builder not found: {script}")
    completed = subprocess.run(
        [sys.executable, str(script)],
        cwd=ROOT_DIR / "backend",
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
        raise RuntimeError(f"Seed regeneration failed: {detail}")


def _apply_result(db: Session, item: FifaGroupResult, warnings: list[str]) -> str:
    match = db.scalar(select(Match).where(Match.official_match_number == item.match_number))
    if match is None:
        warnings.append(f"Unknown match number {item.match_number} from FIFA feed")
        return "skipped"

    if match.team_a_id is None or match.team_b_id is None:
        warnings.append(f"Match {item.match_number} is missing team assignments")
        return "skipped"

    team_a = db.get(Team, match.team_a_id)
    team_b = db.get(Team, match.team_b_id)
    if team_a is None or team_b is None:
        warnings.append(f"Match {item.match_number} is missing team assignments")
        return "skipped"

    expected = {team_a.fifa_code, team_b.fifa_code}
    actual = {item.team_a_code, item.team_b_code}
    if expected != actual:
        warnings.append(
            f"Match {item.match_number} team mismatch: expected {sorted(expected)}, got {sorted(actual)}"
        )
        return "skipped"

    current = db.scalar(select(MatchResult).where(
        MatchResult.match_id == match.id,
        MatchResult.is_current.is_(True),
    ))
    if current and current.team_a_goals_90 == item.goals_a and current.team_b_goals_90 == item.goals_b:
        if match.status != "final":
            match.status = "final"
        return "skipped"

    payload = {
        "team_a_goals_90": item.goals_a,
        "team_b_goals_90": item.goals_b,
        "source": "fifa.com-api-v3",
    }
    revise_result(db, match.id, payload)
    return "applied"
