from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from world_cup_api.config import get_settings

WORLD_CUP_COMPETITION_ID = "17"
WORLD_CUP_SEASON_ID = "285023"
FINISHED_STATUSES = {0}


@dataclass(frozen=True)
class FifaGroupResult:
    match_number: int
    team_a_code: str
    team_b_code: str
    goals_a: int
    goals_b: int
    status: int


def fetch_finished_group_results(
    *,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[FifaGroupResult]:
    settings = get_settings()
    from_day = from_date or date(2026, 6, 11)
    to_day = to_date or date(2026, 7, 19)
    params = urlencode({
        "from": f"{from_day.isoformat()}T00:00:00Z",
        "to": f"{to_day.isoformat()}T23:59:59Z",
        "count": 500,
        "offset": 0,
        "language": "en",
        "idCompetition": WORLD_CUP_COMPETITION_ID,
        "idSeason": WORLD_CUP_SEASON_ID,
    })
    url = f"{settings.fifa_api_base.rstrip('/')}/calendar/matches?{params}"
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "world-cup-forecast/0.1"})
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"FIFA match fetch failed: {exc}") from exc

    finished: list[FifaGroupResult] = []
    for row in payload.get("Results", []):
        match_number = row.get("MatchNumber")
        if not isinstance(match_number, int) or match_number > 72:
            continue
        if row.get("MatchStatus") not in FINISHED_STATUSES:
            continue
        goals_a = row.get("HomeTeamScore")
        goals_b = row.get("AwayTeamScore")
        if goals_a is None or goals_b is None:
            continue
        finished.append(FifaGroupResult(
            match_number=match_number,
            team_a_code=row["Home"]["Abbreviation"],
            team_b_code=row["Away"]["Abbreviation"],
            goals_a=int(goals_a),
            goals_b=int(goals_b),
            status=int(row["MatchStatus"]),
        ))
    return sorted(finished, key=lambda item: item.match_number)
