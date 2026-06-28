from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ReportTeams:
    home_team: str
    away_team: str

    @classmethod
    def from_manifest(cls, home_team: str | None, away_team: str | None) -> ReportTeams | None:
        if not home_team or not away_team:
            return None
        return cls(home_team=home_team.strip(), away_team=away_team.strip())

    def side_pairs(self) -> tuple[tuple[str, str], tuple[str, str]]:
        return (("left", self.home_team), ("right", self.away_team))

    def compact_header(self, section: str) -> str:
        return re.sub(r"[^a-z]", "", f"{section}{self.home_team}v{self.away_team}".lower())

    def matches_scope(self, text: str) -> str | None:
        first = re.sub(r"\s+", " ", text.replace("\x00", "f")).strip()[:180]
        found = [
            team
            for team in (self.home_team, self.away_team)
            if re.search(rf"\b{re.escape(team)}\b", first, flags=re.IGNORECASE)
        ]
        if len(found) == 1:
            return found[0]
        return None
