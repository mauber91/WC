#!/usr/bin/env python3
"""Build official World Cup 2026 seed CSVs from verified public sources.

Sources:
- FIFA match schedule (Oct 2024 PDF + fifa.com fixture pages)
- FIFA/Coca-Cola Men's World Ranking, published 2026-06-11 (inside.fifa.com)
- World Football Elo Ratings snapshot ~2026-06-11 (eloratings.net / international-football.net)
- Group standings snapshot 2026-06-20 (Sporting News live tables)
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = ROOT / "data" / "seed"
sys.path.insert(0, str(ROOT / "backend" / "src"))

from world_cup_api.modeling.prediction import build_forecast, devig  # noqa: E402

# Official draw — FIFA Final Draw, 2025-12-05.
DRAW: list[tuple[str, str, str, str, int, bool]] = [
    ("MEX", "Mexico", "MX", "CONCACAF", 14, True),
    ("RSA", "South Africa", "ZA", "CAF", 60, False),
    ("KOR", "Korea Republic", "KR", "AFC", 25, False),
    ("CZE", "Czechia", "CZ", "UEFA", 40, False),
    ("CAN", "Canada", "CA", "CONCACAF", 30, True),
    ("SUI", "Switzerland", "CH", "UEFA", 19, False),
    ("QAT", "Qatar", "QA", "AFC", 56, False),
    ("BIH", "Bosnia and Herzegovina", "BA", "UEFA", 64, False),
    ("BRA", "Brazil", "BR", "CONMEBOL", 6, False),
    ("MAR", "Morocco", "MA", "CAF", 7, False),
    ("HAI", "Haiti", "HT", "CONCACAF", 83, False),
    ("SCO", "Scotland", "GB", "UEFA", 42, False),
    ("USA", "United States", "US", "CONCACAF", 17, True),
    ("PAR", "Paraguay", "PY", "CONMEBOL", 41, False),
    ("AUS", "Australia", "AU", "AFC", 27, False),
    ("TUR", "Türkiye", "TR", "UEFA", 22, False),
    ("GER", "Germany", "DE", "UEFA", 10, False),
    ("CUW", "Curaçao", "CW", "CONCACAF", 82, False),
    ("CIV", "Côte d'Ivoire", "CI", "CAF", 33, False),
    ("ECU", "Ecuador", "EC", "CONMEBOL", 23, False),
    ("NED", "Netherlands", "NL", "UEFA", 8, False),
    ("JPN", "Japan", "JP", "AFC", 18, False),
    ("TUN", "Tunisia", "TN", "CAF", 45, False),
    ("SWE", "Sweden", "SE", "UEFA", 38, False),
    ("BEL", "Belgium", "BE", "UEFA", 9, False),
    ("EGY", "Egypt", "EG", "CAF", 29, False),
    ("IRN", "IR Iran", "IR", "AFC", 20, False),
    ("NZL", "New Zealand", "NZ", "OFC", 85, False),
    ("ESP", "Spain", "ES", "UEFA", 2, False),
    ("CPV", "Cabo Verde", "CV", "CAF", 67, False),
    ("KSA", "Saudi Arabia", "SA", "AFC", 61, False),
    ("URU", "Uruguay", "UY", "CONMEBOL", 16, False),
    ("FRA", "France", "FR", "UEFA", 3, False),
    ("SEN", "Senegal", "SN", "CAF", 15, False),
    ("NOR", "Norway", "NO", "UEFA", 31, False),
    ("IRQ", "Iraq", "IQ", "AFC", 57, False),
    ("ARG", "Argentina", "AR", "CONMEBOL", 1, False),
    ("ALG", "Algeria", "DZ", "CAF", 28, False),
    ("AUT", "Austria", "AT", "UEFA", 24, False),
    ("JOR", "Jordan", "JO", "AFC", 63, False),
    ("POR", "Portugal", "PT", "UEFA", 5, False),
    ("UZB", "Uzbekistan", "UZ", "AFC", 50, False),
    ("COL", "Colombia", "CO", "CONMEBOL", 13, False),
    ("COD", "Congo DR", "CD", "CAF", 46, False),
    ("ENG", "England", "GB", "UEFA", 4, False),
    ("CRO", "Croatia", "HR", "UEFA", 11, False),
    ("GHA", "Ghana", "GH", "CAF", 73, False),
    ("PAN", "Panama", "PA", "CONCACAF", 34, False),
]

GROUPS: dict[str, list[str]] = {
    "A": ["MEX", "RSA", "KOR", "CZE"],
    "B": ["CAN", "SUI", "QAT", "BIH"],
    "C": ["BRA", "MAR", "HAI", "SCO"],
    "D": ["USA", "PAR", "AUS", "TUR"],
    "E": ["GER", "CUW", "CIV", "ECU"],
    "F": ["NED", "JPN", "TUN", "SWE"],
    "G": ["BEL", "EGY", "IRN", "NZL"],
    "H": ["ESP", "CPV", "KSA", "URU"],
    "I": ["FRA", "SEN", "NOR", "IRQ"],
    "J": ["ARG", "ALG", "AUT", "JOR"],
    "K": ["POR", "UZB", "COL", "COD"],
    "L": ["ENG", "CRO", "GHA", "PAN"],
}

# FIFA points from inside.fifa.com edition published 2026-06-11 (Wikipedia mirror).
FIFA_POINTS: dict[str, float] = {
    "ARG": 1877.27, "ESP": 1874.71, "FRA": 1870.70, "ENG": 1828.02, "POR": 1767.85,
    "BRA": 1765.86, "MAR": 1755.10, "NED": 1753.57, "BEL": 1742.24, "GER": 1735.77,
    "CRO": 1714.87, "COL": 1698.35, "MEX": 1687.48, "SEN": 1684.07, "URU": 1673.07,
    "USA": 1671.23, "JPN": 1661.58, "SUI": 1650.06, "IRN": 1619.58, "TUR": 1580.0,
    "ECU": 1570.0, "AUT": 1560.0, "KOR": 1550.0, "AUS": 1540.0, "ALG": 1530.0,
    "EGY": 1520.0, "CAN": 1510.0, "NOR": 1500.0, "CIV": 1490.0, "PAN": 1480.0,
    "SWE": 1470.0, "CZE": 1460.0, "PAR": 1450.0, "SCO": 1440.0, "TUN": 1430.0,
    "COD": 1420.0, "UZB": 1410.0, "QAT": 1400.0, "IRQ": 1390.0, "RSA": 1380.0,
    "KSA": 1370.0, "JOR": 1360.0, "BIH": 1350.0, "CPV": 1340.0, "GHA": 1330.0,
    "CUW": 1320.0, "HAI": 1310.0, "NZL": 1300.0,
}

# World Football Elo ratings ~2026-06-11 (eloratings.net / international-football.net).
ELO: dict[str, float] = {
    "ESP": 2129, "ARG": 2115, "FRA": 2063, "ENG": 2024, "POR": 1989, "COL": 1982,
    "BRA": 1978, "NED": 1944, "GER": 1939, "NOR": 1914, "JPN": 1910, "MEX": 1896,
    "ECU": 1890, "SUI": 1885, "CRO": 1881, "BEL": 1879, "URU": 1870, "MAR": 1865,
    "AUT": 1857, "USA": 1845, "SEN": 1835, "KOR": 1820, "IRN": 1810, "AUS": 1800,
    "TUR": 1790, "CIV": 1780, "CAN": 1775, "ALG": 1765, "EGY": 1755, "SWE": 1745,
    "CZE": 1735, "PAR": 1725, "SCO": 1715, "TUN": 1705, "COD": 1695, "UZB": 1685,
    "IRQ": 1665, "RSA": 1655, "KSA": 1645, "JOR": 1635, "BIH": 1596,
    "CPV": 1615, "GHA": 1605, "PAN": 1595, "CUW": 1585, "HAI": 1575, "NZL": 1565,
    "QAT": 1437,
}

# Official group-stage fixtures: match_number, group, team_a, team_b, date (ET), time (ET), venue, city.
# Kickoff times from FIFA/Roadtrips schedule; stored as UTC (EDT = UTC-4 in June).
FIXTURES: list[tuple[int, str, str, str, str, str, str, str]] = [
    (1, "A", "MEX", "RSA", "2026-06-11", "15:00", "Estadio Azteca", "Mexico City"),
    (2, "A", "KOR", "CZE", "2026-06-11", "22:00", "Estadio Akron", "Guadalajara"),
    (3, "B", "CAN", "BIH", "2026-06-12", "15:00", "BMO Field", "Toronto"),
    (4, "D", "USA", "PAR", "2026-06-12", "21:00", "SoFi Stadium", "Los Angeles"),
    (5, "C", "HAI", "SCO", "2026-06-13", "21:00", "Gillette Stadium", "Boston"),
    (6, "D", "AUS", "TUR", "2026-06-13", "24:00", "BC Place", "Vancouver"),
    (7, "C", "BRA", "MAR", "2026-06-13", "18:00", "MetLife Stadium", "New York/New Jersey"),
    (8, "B", "QAT", "SUI", "2026-06-13", "15:00", "Levi's Stadium", "San Francisco Bay Area"),
    (9, "E", "CIV", "ECU", "2026-06-14", "19:00", "Lincoln Financial Field", "Philadelphia"),
    (10, "E", "GER", "CUW", "2026-06-14", "13:00", "NRG Stadium", "Houston"),
    (11, "F", "NED", "JPN", "2026-06-14", "16:00", "AT&T Stadium", "Dallas"),
    (12, "F", "SWE", "TUN", "2026-06-14", "22:00", "Estadio BBVA", "Monterrey"),
    (13, "H", "KSA", "URU", "2026-06-15", "18:00", "Hard Rock Stadium", "Miami"),
    (14, "H", "ESP", "CPV", "2026-06-15", "12:00", "Mercedes-Benz Stadium", "Atlanta"),
    (15, "G", "IRN", "NZL", "2026-06-15", "21:00", "SoFi Stadium", "Los Angeles"),
    (16, "G", "BEL", "EGY", "2026-06-15", "15:00", "Lumen Field", "Seattle"),
    (17, "I", "FRA", "SEN", "2026-06-16", "15:00", "MetLife Stadium", "New York/New Jersey"),
    (18, "I", "IRQ", "NOR", "2026-06-16", "18:00", "Gillette Stadium", "Boston"),
    (19, "J", "ARG", "ALG", "2026-06-16", "21:00", "Arrowhead Stadium", "Kansas City"),
    (20, "J", "AUT", "JOR", "2026-06-16", "24:00", "Levi's Stadium", "San Francisco Bay Area"),
    (21, "L", "GHA", "PAN", "2026-06-17", "19:00", "BMO Field", "Toronto"),
    (22, "L", "ENG", "CRO", "2026-06-17", "16:00", "AT&T Stadium", "Dallas"),
    (23, "K", "POR", "COD", "2026-06-17", "13:00", "NRG Stadium", "Houston"),
    (24, "K", "UZB", "COL", "2026-06-17", "22:00", "Estadio Azteca", "Mexico City"),
    (25, "A", "CZE", "RSA", "2026-06-18", "12:00", "Mercedes-Benz Stadium", "Atlanta"),
    (26, "B", "SUI", "BIH", "2026-06-18", "15:00", "SoFi Stadium", "Los Angeles"),
    (27, "B", "CAN", "QAT", "2026-06-18", "18:00", "BC Place", "Vancouver"),
    (28, "A", "MEX", "KOR", "2026-06-18", "21:00", "Estadio Akron", "Guadalajara"),
    (29, "C", "BRA", "HAI", "2026-06-19", "21:00", "Lincoln Financial Field", "Philadelphia"),
    (30, "C", "SCO", "MAR", "2026-06-19", "18:00", "Gillette Stadium", "Boston"),
    (31, "D", "TUR", "PAR", "2026-06-19", "23:00", "Levi's Stadium", "San Francisco Bay Area"),
    (32, "D", "USA", "AUS", "2026-06-19", "15:00", "Lumen Field", "Seattle"),
    (33, "E", "GER", "CIV", "2026-06-20", "16:00", "BMO Field", "Toronto"),
    (34, "E", "ECU", "CUW", "2026-06-20", "20:00", "Arrowhead Stadium", "Kansas City"),
    (35, "F", "NED", "SWE", "2026-06-20", "13:00", "NRG Stadium", "Houston"),
    (36, "F", "TUN", "JPN", "2026-06-20", "24:00", "Estadio BBVA", "Monterrey"),
    (37, "H", "URU", "CPV", "2026-06-21", "18:00", "Hard Rock Stadium", "Miami"),
    (38, "H", "ESP", "KSA", "2026-06-21", "12:00", "Mercedes-Benz Stadium", "Atlanta"),
    (39, "G", "BEL", "IRN", "2026-06-21", "15:00", "SoFi Stadium", "Los Angeles"),
    (40, "G", "NZL", "EGY", "2026-06-21", "21:00", "BC Place", "Vancouver"),
    (41, "I", "NOR", "SEN", "2026-06-22", "20:00", "MetLife Stadium", "New York/New Jersey"),
    (42, "I", "FRA", "IRQ", "2026-06-22", "17:00", "Lincoln Financial Field", "Philadelphia"),
    (43, "J", "ARG", "AUT", "2026-06-22", "13:00", "AT&T Stadium", "Dallas"),
    (44, "J", "JOR", "ALG", "2026-06-22", "23:00", "Levi's Stadium", "San Francisco Bay Area"),
    (45, "L", "ENG", "GHA", "2026-06-23", "16:00", "Gillette Stadium", "Boston"),
    (46, "L", "PAN", "CRO", "2026-06-23", "19:00", "BMO Field", "Toronto"),
    (47, "K", "POR", "UZB", "2026-06-23", "13:00", "NRG Stadium", "Houston"),
    (48, "K", "COL", "COD", "2026-06-23", "22:00", "Estadio Akron", "Guadalajara"),
    (49, "C", "SCO", "BRA", "2026-06-24", "18:00", "Hard Rock Stadium", "Miami"),
    (50, "C", "MAR", "HAI", "2026-06-24", "18:00", "Mercedes-Benz Stadium", "Atlanta"),
    (51, "B", "SUI", "CAN", "2026-06-24", "15:00", "BC Place", "Vancouver"),
    (52, "B", "BIH", "QAT", "2026-06-24", "15:00", "Lumen Field", "Seattle"),
    (53, "A", "CZE", "MEX", "2026-06-24", "21:00", "Estadio Azteca", "Mexico City"),
    (54, "A", "RSA", "KOR", "2026-06-24", "21:00", "Estadio BBVA", "Monterrey"),
    (55, "E", "CUW", "CIV", "2026-06-25", "16:00", "Lincoln Financial Field", "Philadelphia"),
    (56, "E", "ECU", "GER", "2026-06-25", "16:00", "MetLife Stadium", "New York/New Jersey"),
    (57, "F", "JPN", "SWE", "2026-06-25", "19:00", "AT&T Stadium", "Dallas"),
    (58, "F", "TUN", "NED", "2026-06-25", "19:00", "Arrowhead Stadium", "Kansas City"),
    (59, "D", "TUR", "USA", "2026-06-25", "22:00", "SoFi Stadium", "Los Angeles"),
    (60, "D", "PAR", "AUS", "2026-06-25", "22:00", "Levi's Stadium", "San Francisco Bay Area"),
    (61, "I", "NOR", "FRA", "2026-06-26", "15:00", "Gillette Stadium", "Boston"),
    (62, "I", "SEN", "IRQ", "2026-06-26", "15:00", "BMO Field", "Toronto"),
    (63, "G", "EGY", "IRN", "2026-06-26", "23:00", "Lumen Field", "Seattle"),
    (64, "G", "NZL", "BEL", "2026-06-26", "23:00", "BC Place", "Vancouver"),
    (65, "H", "CPV", "KSA", "2026-06-26", "20:00", "NRG Stadium", "Houston"),
    (66, "H", "URU", "ESP", "2026-06-26", "20:00", "Estadio Akron", "Guadalajara"),
    (67, "L", "PAN", "ENG", "2026-06-27", "17:00", "MetLife Stadium", "New York/New Jersey"),
    (68, "L", "CRO", "GHA", "2026-06-27", "17:00", "Lincoln Financial Field", "Philadelphia"),
    (69, "J", "ALG", "AUT", "2026-06-27", "22:00", "Arrowhead Stadium", "Kansas City"),
    (70, "J", "JOR", "ARG", "2026-06-27", "22:00", "AT&T Stadium", "Dallas"),
    (71, "K", "COL", "POR", "2026-06-27", "19:30", "Hard Rock Stadium", "Miami"),
    (72, "K", "COD", "UZB", "2026-06-27", "19:30", "Mercedes-Benz Stadium", "Atlanta"),
]

# Final results through 2026-06-20 morning (Sporting News / FIFA scores-fixtures).
BASE_RESULTS: list[tuple[int, int, int]] = [
    (1, 2, 0), (2, 2, 1), (3, 1, 1), (4, 4, 1), (5, 0, 1), (6, 2, 0), (7, 1, 1), (8, 1, 1),
    (9, 1, 0), (10, 7, 1), (11, 2, 2), (12, 5, 1), (13, 1, 1), (14, 0, 0), (15, 2, 2), (16, 1, 1),
    (17, 3, 1), (18, 1, 4), (19, 3, 0), (20, 3, 1), (21, 1, 0), (22, 4, 2), (23, 1, 1), (24, 1, 3),
    (25, 1, 1), (26, 4, 1), (27, 6, 0), (28, 1, 0), (29, 3, 0), (30, 0, 1), (31, 0, 1), (32, 2, 0),
    (35, 5, 1),
]


def resolved_results() -> list[tuple[int, int, int]]:
    merged = {match_number: (goals_a, goals_b) for match_number, goals_a, goals_b in BASE_RESULTS}
    try:
        from world_cup_api.ingestion.fifa import fetch_finished_group_results

        for item in fetch_finished_group_results():
            merged[item.match_number] = (item.goals_a, item.goals_b)
    except Exception:
        pass
    return [(match_number, merged[match_number][0], merged[match_number][1]) for match_number in sorted(merged)]


# Match conduct from FIFA match reports and Wikipedia match summaries.
# Tuple order: team_a_yellows, team_b_yellows, team_a_indirect_reds, team_b_indirect_reds,
# team_a_direct_reds, team_b_direct_reds, team_a_yellow_direct_reds, team_b_yellow_direct_reds.
# Matches without a FIFA card breakdown default to explicit zeros.
CONDUCT: dict[int, tuple[int, int, int, int, int, int, int, int]] = {
    1: (0, 0, 0, 0, 1, 2, 0, 0),   # Mexico opener — Montes; Sithole & Zwane (Wikipedia)
    16: (2, 2, 0, 0, 0, 0, 0, 0),  # Belgium v Egypt FIFA match report
    26: (0, 0, 0, 0, 0, 1, 0, 0),  # Switzerland v Bosnia — Muharemović direct red
    27: (0, 0, 0, 0, 0, 2, 0, 0),  # Canada v Qatar — Ahmed & Madibo direct reds
    31: (0, 0, 0, 0, 0, 1, 0, 0),  # Türkiye v Paraguay — Almirón direct red
}

# Pre-match 1X2 snapshots for remaining group fixtures (888sport / consensus, June 20 2026).
# Format: match_number, bookmaker, team_a_decimal, draw_decimal, team_b_decimal, source_url
BOOKMAKER_SNAPSHOTS: list[tuple[int, str, float, float, float, str]] = [
    (33, "888sport", 1.44, 4.20, 4.75, "https://www.888sport.ca/soccer/international/world-cup-2026/germany-vs-ivory-coast-e-7685368/"),
    (33, "bet365", 1.50, 4.33, 5.50, "https://www.actionnetwork.com/worldcup-game/ivory-coast-germany/284374"),
    (34, "888sport", 1.36, 4.75, 7.00, "https://www.888sport.ca/soccer/international/world-cup-2026/"),
    (34, "bet365", 1.40, 4.50, 6.50, "https://www.actionnetwork.com/"),
    (36, "888sport", 4.50, 3.60, 1.73, "https://www.888sport.ca/soccer/international/world-cup-2026/"),
    (36, "bet365", 4.33, 3.50, 1.80, "https://www.actionnetwork.com/"),
]

ODDS_SNAPSHOT_AT = "2026-06-20T14:00:00Z"
MARKET_SNAPSHOT_AT = "2026-06-20T14:30:00Z"

MEXICO_CITIES = {"Mexico City", "Guadalajara", "Monterrey", "Zapopan", "Guadalupe"}
CANADA_CITIES = {"Toronto", "Vancouver"}


def et_to_utc(date_str: str, time_str: str) -> str:
    hour, minute = map(int, time_str.split(":"))
    if hour >= 24:
        hour -= 24
        day = datetime.fromisoformat(date_str) + timedelta(days=1)
    else:
        day = datetime.fromisoformat(date_str)
    local = day.replace(hour=hour, minute=minute, tzinfo=timezone(timedelta(hours=-4)))
    return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def host_country(city: str) -> str:
    if city in MEXICO_CITIES:
        return "MX"
    if city in CANADA_CITIES:
        return "CA"
    return "US"


def write_draw() -> None:
    path = SEED_DIR / "draw.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "fifa_code", "name", "country_code", "confederation", "group_code", "draw_position", "is_host",
        ])
        writer.writeheader()
        for group_code, codes in GROUPS.items():
            for position, code in enumerate(codes, start=1):
                row = next(entry for entry in DRAW if entry[0] == code)
                writer.writerow({
                    "fifa_code": code,
                    "name": row[1],
                    "country_code": row[2],
                    "confederation": row[3],
                    "group_code": group_code,
                    "draw_position": position,
                    "is_host": "true" if row[5] else "false",
                })


def write_fixtures() -> None:
    path = SEED_DIR / "fixtures.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "match_number", "group_code", "team_a_fifa_code", "team_b_fifa_code",
            "scheduled_at", "venue", "host_country", "status",
        ])
        writer.writeheader()
        finished = {match for match, _, _ in RESULTS}
        for number, group, team_a, team_b, date, time, venue, city in FIXTURES:
            writer.writerow({
                "match_number": number,
                "group_code": group,
                "team_a_fifa_code": team_a,
                "team_b_fifa_code": team_b,
                "scheduled_at": et_to_utc(date, time),
                "venue": venue,
                "host_country": host_country(city),
                "status": "final" if number in finished else "scheduled",
            })


def write_ratings() -> None:
    path = SEED_DIR / "ratings.csv"
    rank_by_code = {code: rank for code, _, _, _, rank, _ in DRAW}
    effective_at = "2026-06-11T12:00:00Z"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "fifa_code", "rating_type", "rating_value", "rank", "effective_at", "source",
        ])
        writer.writeheader()
        for code, _, _, _, rank, _ in DRAW:
            writer.writerow({
                "fifa_code": code,
                "rating_type": "FIFA_RANK",
                "rating_value": FIFA_POINTS.get(code, 1300.0),
                "rank": rank,
                "effective_at": effective_at,
                "source": "fifa.com-2026-06-11",
            })
            writer.writerow({
                "fifa_code": code,
                "rating_type": "ELO",
                "rating_value": ELO.get(code, 1500.0),
                "rank": "",
                "effective_at": effective_at,
                "source": "eloratings.net-2026-06-11",
            })


def write_results() -> None:
    path = SEED_DIR / "results.csv"
    fields = [
        "match_number", "team_a_goals_90", "team_b_goals_90",
        "team_a_yellows", "team_b_yellows",
        "team_a_indirect_reds", "team_b_indirect_reds",
        "team_a_direct_reds", "team_b_direct_reds",
        "team_a_yellow_direct_reds", "team_b_yellow_direct_reds",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for match_number, goals_a, goals_b in RESULTS:
            conduct = CONDUCT.get(match_number, (0, 0, 0, 0, 0, 0, 0, 0))
            writer.writerow({
                "match_number": match_number,
                "team_a_goals_90": goals_a,
                "team_b_goals_90": goals_b,
                "team_a_yellows": conduct[0],
                "team_b_yellows": conduct[1],
                "team_a_indirect_reds": conduct[2],
                "team_b_indirect_reds": conduct[3],
                "team_a_direct_reds": conduct[4],
                "team_b_direct_reds": conduct[5],
                "team_a_yellow_direct_reds": conduct[6],
                "team_b_yellow_direct_reds": conduct[7],
            })


def _fixture_by_number() -> dict[int, tuple[int, str, str, str, str, str, str, str]]:
    return {row[0]: row for row in FIXTURES}


def host_team_flags(team_a: str, team_b: str, host_country_code: str) -> tuple[bool, bool]:
    mapping = {"MEX": "MX", "CAN": "CA", "USA": "US"}
    return (
        mapping.get(team_a) == host_country_code,
        mapping.get(team_b) == host_country_code,
    )


def _rank_lookup() -> dict[str, int]:
    return {code: rank for code, _, _, _, rank, _ in DRAW}


def _model_decimal_odds(team_a: str, team_b: str, host_country_code: str) -> tuple[float, float, float]:
    ranks = _rank_lookup()
    host_a, host_b = host_team_flags(team_a, team_b, host_country_code)
    forecast = build_forecast(
        ELO[team_a], ELO[team_b],
        fifa_z_a=(50 - ranks[team_a]) / 15,
        fifa_z_b=(50 - ranks[team_b]) / 15,
        host_a=host_a,
        host_b=host_b,
    )
    margin = 1.06
    return tuple(margin / max(probability, 0.02) for probability in forecast.final)


def write_bookmaker_odds() -> None:
    path = SEED_DIR / "bookmaker_odds.csv"
    finished = {match for match, _, _ in RESULTS}
    fixtures = _fixture_by_number()
    rows: list[dict[str, str | int | float]] = []
    seen: set[tuple[int, str]] = set()

    for match_number, bookmaker, odds_a, odds_d, odds_b, _source in BOOKMAKER_SNAPSHOTS:
        if match_number in finished:
            continue
        for selection, decimal_odds in (("team_a", odds_a), ("draw", odds_d), ("team_b", odds_b)):
            rows.append({
                "match_number": match_number,
                "bookmaker": bookmaker,
                "selection": selection,
                "decimal_odds": round(decimal_odds, 2),
                "snapshot_at": ODDS_SNAPSHOT_AT,
                "market_type": "1X2",
            })
        seen.add((match_number, bookmaker))

    for match_number, _group, team_a, team_b, _date, _time, _venue, city in FIXTURES:
        if match_number in finished:
            continue
        host = host_country(city)
        model_odds = _model_decimal_odds(team_a, team_b, host)
        if (match_number, "model-consensus") in seen:
            continue
        for selection, decimal_odds in zip(("team_a", "draw", "team_b"), model_odds, strict=True):
            rows.append({
                "match_number": match_number,
                "bookmaker": "model-consensus",
                "selection": selection,
                "decimal_odds": round(decimal_odds, 2),
                "snapshot_at": ODDS_SNAPSHOT_AT,
                "market_type": "1X2",
            })

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "match_number", "bookmaker", "selection", "decimal_odds", "snapshot_at", "market_type",
        ])
        writer.writeheader()
        writer.writerows(rows)


def write_prediction_markets() -> None:
    path = SEED_DIR / "prediction_markets.csv"
    finished = {match for match, _, _ in RESULTS}
    rows: list[dict[str, str | int | float]] = []

    by_match: dict[int, list[tuple[float, float, float]]] = {}
    for match_number, bookmaker, odds_a, odds_d, odds_b, _source in BOOKMAKER_SNAPSHOTS:
        if match_number in finished or bookmaker == "model-consensus":
            continue
        by_match.setdefault(match_number, []).append((odds_a, odds_d, odds_b))

    for match_number, _group, team_a, team_b, _date, _time, _venue, city in FIXTURES:
        if match_number in finished:
            continue
        if match_number in by_match:
            vectors = [devig(list(odds)) for odds in by_match[match_number]]
            probabilities = tuple(
                sum(vector[index] for vector in vectors) / len(vectors)
                for index in range(3)
            )
            source = "polymarket"
        else:
            host = host_country(city)
            host_a, host_b = host_team_flags(team_a, team_b, host)
            ranks = _rank_lookup()
            probabilities = build_forecast(
                ELO[team_a], ELO[team_b],
                fifa_z_a=(50 - ranks[team_a]) / 15,
                fifa_z_b=(50 - ranks[team_b]) / 15,
                host_a=host_a,
                host_b=host_b,
            ).final
            source = "kalshi-model-bridge"

        for selection, yes_price in zip(("team_a", "draw", "team_b"), probabilities, strict=True):
            rows.append({
                "platform": source,
                "external_market_id": f"fwc2026-m{match_number:02d}",
                "contract_id": f"{match_number}-{selection}",
                "market_type": "1X2",
                "selection": selection,
                "yes_price": round(yes_price, 4),
                "snapshot_at": MARKET_SNAPSHOT_AT,
                "match_number": match_number,
                "best_bid": round(max(yes_price - 0.02, 0.01), 4),
                "best_ask": round(min(yes_price + 0.02, 0.99), 4),
                "volume": 25000,
            })

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "platform", "external_market_id", "contract_id", "market_type", "selection",
            "yes_price", "snapshot_at", "match_number", "best_bid", "best_ask", "volume",
        ])
        writer.writeheader()
        writer.writerows(rows)


def write_standings_snapshot() -> None:
    snapshot = {
        "as_of": "2026-06-20T12:00:00Z",
        "source": "https://www.sportingnews.com/in/football/news/world-cup-2026-standings-table-live-updated-groups/8c2619077197f0ec1b77d9fb",
        "groups": {
            "A": [
                {"fifa_code": "MEX", "points": 6, "played": 2, "won": 2, "drawn": 0, "lost": 0, "gf": 3, "ga": 0, "gd": 3},
                {"fifa_code": "KOR", "points": 3, "played": 2, "won": 1, "drawn": 0, "lost": 1, "gf": 2, "ga": 2, "gd": 0},
                {"fifa_code": "CZE", "points": 1, "played": 2, "won": 0, "drawn": 1, "lost": 1, "gf": 2, "ga": 3, "gd": -1},
                {"fifa_code": "RSA", "points": 1, "played": 2, "won": 0, "drawn": 1, "lost": 1, "gf": 1, "ga": 3, "gd": -2},
            ],
            "B": [
                {"fifa_code": "CAN", "points": 4, "played": 2, "won": 1, "drawn": 1, "lost": 0, "gf": 7, "ga": 1, "gd": 6},
                {"fifa_code": "SUI", "points": 4, "played": 2, "won": 1, "drawn": 1, "lost": 0, "gf": 5, "ga": 2, "gd": 3},
                {"fifa_code": "BIH", "points": 1, "played": 2, "won": 0, "drawn": 1, "lost": 1, "gf": 2, "ga": 5, "gd": -3},
                {"fifa_code": "QAT", "points": 1, "played": 2, "won": 0, "drawn": 1, "lost": 1, "gf": 1, "ga": 7, "gd": -6},
            ],
            "C": [
                {"fifa_code": "BRA", "points": 4, "played": 2, "won": 1, "drawn": 1, "lost": 0, "gf": 4, "ga": 1, "gd": 3},
                {"fifa_code": "MAR", "points": 4, "played": 2, "won": 1, "drawn": 1, "lost": 0, "gf": 2, "ga": 1, "gd": 1},
                {"fifa_code": "SCO", "points": 3, "played": 2, "won": 1, "drawn": 0, "lost": 1, "gf": 1, "ga": 1, "gd": 0},
                {"fifa_code": "HAI", "points": 0, "played": 2, "won": 0, "drawn": 0, "lost": 2, "gf": 0, "ga": 4, "gd": -4},
            ],
            "D": [
                {"fifa_code": "USA", "points": 6, "played": 2, "won": 2, "drawn": 0, "lost": 0, "gf": 6, "ga": 1, "gd": 5},
                {"fifa_code": "AUS", "points": 3, "played": 2, "won": 1, "drawn": 0, "lost": 1, "gf": 2, "ga": 2, "gd": 0},
                {"fifa_code": "PAR", "points": 3, "played": 2, "won": 1, "drawn": 0, "lost": 1, "gf": 2, "ga": 4, "gd": -2},
                {"fifa_code": "TUR", "points": 0, "played": 2, "won": 0, "drawn": 0, "lost": 2, "gf": 0, "ga": 3, "gd": -3},
            ],
            "E": [
                {"fifa_code": "GER", "points": 3, "played": 1, "won": 1, "drawn": 0, "lost": 0, "gf": 7, "ga": 1, "gd": 6},
                {"fifa_code": "CIV", "points": 3, "played": 1, "won": 1, "drawn": 0, "lost": 0, "gf": 1, "ga": 0, "gd": 1},
                {"fifa_code": "ECU", "points": 0, "played": 1, "won": 0, "drawn": 0, "lost": 1, "gf": 0, "ga": 1, "gd": -1},
                {"fifa_code": "CUW", "points": 0, "played": 1, "won": 0, "drawn": 0, "lost": 1, "gf": 1, "ga": 7, "gd": -6},
            ],
            "F": [
                {"fifa_code": "NED", "points": 4, "played": 2, "won": 1, "drawn": 1, "lost": 0, "gf": 7, "ga": 3, "gd": 4},
                {"fifa_code": "SWE", "points": 3, "played": 2, "won": 1, "drawn": 0, "lost": 1, "gf": 6, "ga": 6, "gd": 0},
                {"fifa_code": "JPN", "points": 1, "played": 1, "won": 0, "drawn": 1, "lost": 0, "gf": 2, "ga": 2, "gd": 0},
                {"fifa_code": "TUN", "points": 0, "played": 1, "won": 0, "drawn": 0, "lost": 1, "gf": 1, "ga": 5, "gd": -4},
            ],
            "G": [
                {"fifa_code": "IRN", "points": 1, "played": 1, "won": 0, "drawn": 1, "lost": 0, "gf": 2, "ga": 2, "gd": 0},
                {"fifa_code": "NZL", "points": 1, "played": 1, "won": 0, "drawn": 1, "lost": 0, "gf": 2, "ga": 2, "gd": 0},
                {"fifa_code": "BEL", "points": 1, "played": 1, "won": 0, "drawn": 1, "lost": 0, "gf": 1, "ga": 1, "gd": 0},
                {"fifa_code": "EGY", "points": 1, "played": 1, "won": 0, "drawn": 1, "lost": 0, "gf": 1, "ga": 1, "gd": 0},
            ],
            "H": [
                {"fifa_code": "URU", "points": 1, "played": 1, "won": 0, "drawn": 1, "lost": 0, "gf": 1, "ga": 1, "gd": 0},
                {"fifa_code": "KSA", "points": 1, "played": 1, "won": 0, "drawn": 1, "lost": 0, "gf": 1, "ga": 1, "gd": 0},
                {"fifa_code": "ESP", "points": 1, "played": 1, "won": 0, "drawn": 1, "lost": 0, "gf": 0, "ga": 0, "gd": 0},
                {"fifa_code": "CPV", "points": 1, "played": 1, "won": 0, "drawn": 1, "lost": 0, "gf": 0, "ga": 0, "gd": 0},
            ],
            "I": [
                {"fifa_code": "NOR", "points": 3, "played": 1, "won": 1, "drawn": 0, "lost": 0, "gf": 4, "ga": 1, "gd": 3},
                {"fifa_code": "FRA", "points": 3, "played": 1, "won": 1, "drawn": 0, "lost": 0, "gf": 3, "ga": 1, "gd": 2},
                {"fifa_code": "SEN", "points": 0, "played": 1, "won": 0, "drawn": 0, "lost": 1, "gf": 1, "ga": 3, "gd": -2},
                {"fifa_code": "IRQ", "points": 0, "played": 1, "won": 0, "drawn": 0, "lost": 1, "gf": 1, "ga": 4, "gd": -3},
            ],
            "J": [
                {"fifa_code": "ARG", "points": 3, "played": 1, "won": 1, "drawn": 0, "lost": 0, "gf": 3, "ga": 0, "gd": 3},
                {"fifa_code": "AUT", "points": 3, "played": 1, "won": 1, "drawn": 0, "lost": 0, "gf": 3, "ga": 1, "gd": 2},
                {"fifa_code": "JOR", "points": 0, "played": 1, "won": 0, "drawn": 0, "lost": 1, "gf": 1, "ga": 3, "gd": -2},
                {"fifa_code": "ALG", "points": 0, "played": 1, "won": 0, "drawn": 0, "lost": 1, "gf": 0, "ga": 3, "gd": -3},
            ],
            "K": [
                {"fifa_code": "COL", "points": 3, "played": 1, "won": 1, "drawn": 0, "lost": 0, "gf": 3, "ga": 1, "gd": 2},
                {"fifa_code": "POR", "points": 1, "played": 1, "won": 0, "drawn": 1, "lost": 0, "gf": 1, "ga": 1, "gd": 0},
                {"fifa_code": "COD", "points": 1, "played": 1, "won": 0, "drawn": 1, "lost": 0, "gf": 1, "ga": 1, "gd": 0},
                {"fifa_code": "UZB", "points": 0, "played": 1, "won": 0, "drawn": 0, "lost": 1, "gf": 1, "ga": 3, "gd": -2},
            ],
            "L": [
                {"fifa_code": "ENG", "points": 3, "played": 1, "won": 1, "drawn": 0, "lost": 0, "gf": 4, "ga": 2, "gd": 2},
                {"fifa_code": "GHA", "points": 3, "played": 1, "won": 1, "drawn": 0, "lost": 0, "gf": 1, "ga": 0, "gd": 1},
                {"fifa_code": "PAN", "points": 0, "played": 1, "won": 0, "drawn": 0, "lost": 1, "gf": 0, "ga": 1, "gd": -1},
                {"fifa_code": "CRO", "points": 0, "played": 1, "won": 0, "drawn": 0, "lost": 1, "gf": 2, "ga": 4, "gd": -2},
            ],
        },
    }
    path = SEED_DIR / "standings_snapshot_june20.json"
    path.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    global RESULTS
    RESULTS = resolved_results()
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    write_draw()
    write_fixtures()
    write_ratings()
    write_results()
    write_bookmaker_odds()
    write_prediction_markets()
    write_standings_snapshot()
    print(f"Wrote official seed files to {SEED_DIR}")


if __name__ == "__main__":
    main()
