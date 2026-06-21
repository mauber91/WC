from __future__ import annotations

import math
import re
from dataclasses import dataclass

from world_cup_api.services.market_sync import TEAM_SEARCH_ALIASES

WC_CHAMPION_RATING_TYPE = "WC_CHAMPION"

# Extra labels seen on Kalshi/Polymarket outright markets.
CHAMPION_LABEL_ALIASES: dict[str, tuple[str, ...]] = {
    **TEAM_SEARCH_ALIASES,
    "ENG": ("England",),
    "FRA": ("France",),
    "ESP": ("Spain",),
    "GER": ("Germany",),
    "BRA": ("Brazil",),
    "ARG": ("Argentina",),
    "POR": ("Portugal",),
    "NED": ("Netherlands",),
    "BEL": ("Belgium",),
    "COL": ("Colombia",),
    "MEX": ("Mexico",),
    "USA": ("United States", "USA"),
    "URU": ("Uruguay",),
    "JPN": ("Japan",),
    "MAR": ("Morocco",),
    "SUI": ("Switzerland",),
    "CRO": ("Croatia",),
    "ECU": ("Ecuador",),
    "SEN": ("Senegal",),
    "NOR": ("Norway",),
    "AUT": ("Austria",),
    "SCO": ("Scotland",),
    "HAI": ("Haiti",),
    "PAN": ("Panama",),
    "KSA": ("Saudi Arabia",),
    "ALG": ("Algeria",),
    "GHA": ("Ghana",),
    "IRQ": ("Iraq",),
    "UZB": ("Uzbekistan",),
    "NZL": ("New Zealand",),
    "RSA": ("South Africa",),
    "PAR": ("Paraguay",),
    "CAN": ("Canada",),
    "EGY": ("Egypt",),
    "TUN": ("Tunisia",),
    "SWE": ("Sweden",),
    "CZE": ("Czechia",),
    "BIH": ("Bosnia and Herzegovina", "Bosnia-Herzegovina"),
    "JOR": ("Jordan",),
    "QAT": ("Qatar",),
    "IRN": ("Iran", "IR Iran"),
    "AUS": ("Australia",),
    "KOR": ("Korea Republic", "South Korea"),
}

_POLYMARKET_QUESTION = re.compile(r"^Will (.+?) win the 2026 FIFA World Cup\?$", re.IGNORECASE)


@dataclass(frozen=True)
class ChampionQuote:
    platform: str
    team_label: str
    yes_price: float
    external_id: str


def _normalize_label(label: str) -> str:
    return " ".join(label.lower().replace("'", "'").split())


def _labels_for_fifa_code(fifa_code: str, team_name: str) -> set[str]:
    labels = {_normalize_label(team_name)}
    for alias in CHAMPION_LABEL_ALIASES.get(fifa_code, ()):
        labels.add(_normalize_label(alias))
    return labels


def build_fifa_label_index(teams: list) -> dict[str, str]:
    """Map normalized market labels to FIFA codes for tournament teams."""
    index: dict[str, str] = {}
    for team in teams:
        for label in _labels_for_fifa_code(team.fifa_code, team.name):
            index[label] = team.fifa_code
    return index


def parse_polymarket_team_label(question: str) -> str | None:
    match = _POLYMARKET_QUESTION.match(question.strip())
    if match is None:
        return None
    return match.group(1).strip()


def match_champion_label(label: str, label_index: dict[str, str]) -> str | None:
    return label_index.get(_normalize_label(label))


def pool_champion_probability(probabilities: list[float]) -> float | None:
    values = [max(float(value), 1e-8) for value in probabilities if value is not None and value > 0]
    if not values:
        return None
    return math.exp(sum(math.log(value) for value in values) / len(values))


def normalize_champion_probabilities(probabilities: dict[str, float]) -> dict[str, float]:
    total = sum(probabilities.values())
    if total <= 0:
        return probabilities
    return {code: value / total for code, value in probabilities.items()}


def champion_probability_to_elo(
    probability: float,
    *,
    field_size: int = 48,
    anchor_elo: float = 1750.0,
    log_scale: float = 55.0,
) -> float:
    """Map outright winner probability to Elo scale (log-odds vs uniform field prior)."""
    baseline = 1.0 / field_size
    probability = max(float(probability), 1e-8)
    return anchor_elo + log_scale * math.log(probability / baseline)
