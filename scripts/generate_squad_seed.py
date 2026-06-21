#!/usr/bin/env python3
"""Deprecated: use scripts/sync_squad_data.py for real squad data."""
raise SystemExit("Use `make squad-data` (scripts/sync_squad_data.py) instead of this synthetic generator.")

from __future__ import annotations

import csv
import hashlib
import random
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = ROOT / "data" / "seed"

SQUAD_SIZE = 26
POSITION_SLOTS = [
    ("GK", 1), ("GK", 13), ("GK", 23),
    ("CB", 2), ("CB", 3), ("CB", 4), ("CB", 5), ("LB", 12), ("RB", 22), ("CB", 15),
    ("CDM", 6), ("CM", 8), ("CM", 10), ("CAM", 11), ("CM", 14), ("CDM", 16), ("LW", 17), ("RW", 19),
    ("ST", 7), ("ST", 9), ("ST", 18), ("ST", 20), ("LW", 21), ("RW", 24), ("ST", 25), ("CM", 26),
]

# Curated squads: (name, position, number, fc26, value_meur, s2425, s2324, s2223)
CURATED: dict[str, list[tuple]] = {
    "ENG": [
        ("Jordan Pickford", "GK", 1, 84, 22, 7.1, 7.0, 6.9),
        ("Kyle Walker", "RB", 2, 81, 12, 6.8, 7.0, 7.1),
        ("Marc Guéhi", "CB", 3, 82, 45, 7.2, 7.0, 6.5),
        ("John Stones", "CB", 5, 84, 28, 7.0, 6.9, 7.2),
        ("Declan Rice", "CDM", 6, 87, 110, 7.4, 7.3, 7.1),
        ("Bukayo Saka", "RW", 7, 88, 120, 7.5, 7.4, 7.2),
        ("Phil Foden", "CAM", 10, 88, 110, 7.3, 7.5, 7.0),
        ("Harry Kane", "ST", 9, 88, 75, 7.6, 7.4, 7.3),
        ("Jude Bellingham", "CM", 8, 91, 180, 7.8, 7.6, 7.0),
        ("Trent Alexander-Arnold", "RB", 22, 86, 65, 7.2, 7.3, 7.4),
        ("Kobbie Mainoo", "CM", 26, 82, 55, 7.0, 6.5, None),
        ("Anthony Gordon", "LW", 21, 83, 60, 7.1, 6.8, 6.4),
    ],
    "FRA": [
        ("Mike Maignan", "GK", 1, 87, 45, 7.2, 7.1, 7.0),
        ("William Saliba", "CB", 2, 87, 80, 7.3, 7.2, 7.0),
        ("Dayot Upamecano", "CB", 4, 84, 50, 7.0, 6.9, 7.0),
        ("N'Golo Kanté", "CDM", 6, 84, 8, 7.0, 6.8, 7.2),
        ("Aurélien Tchouaméni", "CDM", 8, 86, 90, 7.2, 7.1, 6.9),
        ("Kylian Mbappé", "ST", 10, 91, 180, 7.7, 7.6, 7.5),
        ("Ousmane Dembélé", "RW", 11, 86, 60, 7.3, 7.1, 6.8),
        ("Antoine Griezmann", "CAM", 7, 85, 25, 7.2, 7.3, 7.1),
        ("Theo Hernandez", "LB", 3, 86, 55, 7.1, 7.2, 7.0),
        ("Ibrahima Konaté", "CB", 5, 85, 45, 7.0, 6.9, 6.8),
        ("Warren Zaïre-Emery", "CM", 14, 82, 55, 7.0, 6.6, None),
    ],
    "ESP": [
        ("Unai Simón", "GK", 1, 85, 28, 7.1, 7.0, 6.9),
        ("Aymeric Laporte", "CB", 4, 84, 20, 7.0, 6.9, 7.1),
        ("Robin Le Normand", "CB", 3, 83, 35, 7.0, 6.9, 6.7),
        ("Rodri", "CDM", 6, 90, 120, 7.6, 7.5, 7.3),
        ("Pedri", "CM", 8, 87, 100, 7.3, 7.2, 7.0),
        ("Lamine Yamal", "RW", 19, 86, 150, 7.4, 6.8, None),
        ("Nico Williams", "LW", 11, 86, 70, 7.3, 7.0, 6.5),
        ("Álvaro Morata", "ST", 7, 83, 18, 7.0, 6.9, 7.0),
        ("Dani Olmo", "CAM", 10, 85, 55, 7.2, 7.1, 6.9),
        ("Fabián Ruiz", "CM", 14, 84, 40, 7.0, 6.9, 7.0),
        ("Marc Cucurella", "LB", 12, 81, 30, 6.8, 6.7, 6.6),
    ],
    "GER": [
        ("Manuel Neuer", "GK", 1, 85, 5, 7.0, 6.9, 7.1),
        ("Joshua Kimmich", "RB", 6, 87, 50, 7.3, 7.2, 7.1),
        ("Antonio Rüdiger", "CB", 2, 86, 20, 7.1, 7.0, 7.0),
        ("Jonathan Tah", "CB", 4, 84, 35, 7.0, 6.9, 6.8),
        ("Florian Wirtz", "CAM", 10, 88, 130, 7.5, 7.2, 6.5),
        ("Jamal Musiala", "CAM", 11, 88, 120, 7.4, 7.3, 6.8),
        ("Kai Havertz", "ST", 9, 84, 55, 7.0, 6.9, 7.0),
        ("Leroy Sané", "RW", 7, 85, 35, 7.0, 7.1, 7.0),
        ("Ilkay Gündogan", "CM", 8, 84, 12, 7.0, 6.9, 7.2),
        ("Nico Schlotterbeck", "CB", 5, 83, 40, 6.9, 6.8, 6.7),
    ],
    "BRA": [
        ("Alisson", "GK", 1, 89, 25, 7.2, 7.1, 7.0),
        ("Marquinhos", "CB", 4, 87, 35, 7.1, 7.0, 7.1),
        ("Gabriel Magalhães", "CB", 3, 86, 55, 7.2, 7.0, 6.8),
        ("Casemiro", "CDM", 5, 85, 15, 7.0, 6.9, 7.2),
        ("Rodrygo", "RW", 11, 86, 80, 7.2, 7.1, 6.9),
        ("Vinícius Júnior", "LW", 7, 90, 150, 7.5, 7.4, 7.2),
        ("Raphinha", "RW", 22, 85, 50, 7.1, 7.0, 6.8),
        ("Endrick", "ST", 9, 82, 45, 6.8, 6.5, None),
        ("Bruno Guimarães", "CDM", 6, 86, 70, 7.2, 7.1, 7.0),
        ("Raphael Veiga", "CAM", 10, 82, 18, 6.9, 6.8, 6.7),
    ],
    "ARG": [
        ("Emiliano Martínez", "GK", 1, 88, 28, 7.2, 7.1, 7.0),
        ("Cristian Romero", "CB", 2, 85, 50, 7.1, 7.0, 6.9),
        ("Lisandro Martínez", "CB", 3, 84, 40, 7.0, 6.9, 7.0),
        ("Leandro Paredes", "CDM", 5, 82, 12, 6.9, 6.8, 7.0),
        ("Enzo Fernández", "CM", 8, 86, 75, 7.2, 7.1, 6.8),
        ("Alexis Mac Allister", "CM", 14, 85, 55, 7.1, 7.0, 6.7),
        ("Lionel Messi", "RW", 10, 88, 25, 7.4, 7.3, 7.2),
        ("Lautaro Martínez", "ST", 9, 87, 90, 7.3, 7.2, 7.0),
        ("Julián Álvarez", "ST", 11, 85, 70, 7.1, 7.0, 6.8),
        ("Ángel Di María", "LW", 7, 83, 8, 7.0, 6.9, 7.1),
    ],
    "NED": [
        ("Virgil van Dijk", "CB", 4, 88, 35, 7.3, 7.2, 7.1),
        ("Frenkie de Jong", "CM", 8, 86, 60, 7.1, 7.0, 7.2),
        ("Memphis Depay", "ST", 9, 84, 18, 7.0, 6.9, 7.0),
        ("Cody Gakpo", "LW", 11, 84, 45, 7.0, 6.9, 6.8),
        ("Xavi Simons", "CAM", 10, 84, 55, 7.1, 6.8, 6.4),
        ("Matthijs de Ligt", "CB", 3, 84, 40, 6.9, 6.8, 7.0),
    ],
    "POR": [
        ("Diogo Costa", "GK", 1, 84, 40, 7.0, 6.9, 6.7),
        ("Rúben Dias", "CB", 4, 87, 55, 7.2, 7.1, 7.0),
        ("Bruno Fernandes", "CAM", 8, 87, 50, 7.3, 7.2, 7.1),
        ("Bernardo Silva", "CM", 10, 87, 45, 7.2, 7.1, 7.0),
        ("Rafael Leão", "LW", 11, 86, 70, 7.2, 7.0, 6.8),
        ("Cristiano Ronaldo", "ST", 7, 85, 12, 7.0, 6.9, 7.1),
        ("João Félix", "ST", 9, 83, 30, 6.9, 6.8, 7.0),
    ],
    "USA": [
        ("Matt Turner", "GK", 1, 78, 8, 6.7, 6.6, 6.5),
        ("Christian Pulisic", "LW", 10, 83, 45, 7.0, 6.9, 6.8),
        ("Tyler Adams", "CDM", 6, 80, 18, 6.8, 6.7, 6.9),
        ("Weston McKennie", "CM", 8, 81, 22, 6.9, 6.8, 6.7),
        ("Gio Reyna", "CAM", 11, 80, 25, 6.8, 6.7, 6.6),
        ("Folarin Balogun", "ST", 9, 79, 28, 6.7, 6.6, 6.4),
    ],
    "MEX": [
        ("Guillermo Ochoa", "GK", 1, 76, 2, 6.6, 6.5, 6.7),
        ("Edson Álvarez", "CDM", 4, 80, 22, 6.9, 6.8, 6.7),
        ("Hirving Lozano", "LW", 11, 81, 18, 6.9, 6.8, 7.0),
        ("Raúl Jiménez", "ST", 9, 79, 8, 6.7, 6.6, 6.8),
        ("Santiago Giménez", "ST", 7, 80, 35, 6.9, 6.7, 6.3),
    ],
}

FIRST_NAMES = [
    "James", "Lucas", "Marco", "André", "Carlos", "Diego", "Felipe", "Hassan", "Ibrahim", "Jan",
    "Kenji", "Luis", "Mamadou", "Nikola", "Omar", "Pierre", "Quinn", "Ravi", "Samuel", "Tomas",
    "Ugo", "Victor", "Willem", "Youssef", "Zoran",
]
LAST_NAMES = [
    "Silva", "García", "Müller", "Johnson", "Okonkwo", "Petrov", "Santos", "Kim", "Ali", "Brown",
    "Chen", "Dubois", "Eriksson", "Fernandez", "Gonzalez", "Hansen", "Ivanov", "Johansson", "Khan", "Lopez",
]


def _rng(fifa_code: str) -> random.Random:
    digest = hashlib.sha256(fifa_code.encode()).hexdigest()
    return random.Random(int(digest[:16], 16))


def _team_strength(fifa_rank: int) -> float:
    return max(0.35, 1.0 - (fifa_rank - 1) / 70)


def _load_ratings() -> dict[str, int]:
    ranks: dict[str, int] = {}
    with (SEED_DIR / "ratings.csv").open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            if row["rating_type"].upper() == "FIFA_RANK" and row.get("rank"):
                ranks[row["fifa_code"].upper()] = int(row["rank"])
    return ranks


def _load_teams() -> list[str]:
    with (SEED_DIR / "draw.csv").open(newline="", encoding="utf-8-sig") as handle:
        return [row["fifa_code"].upper() for row in csv.DictReader(handle)]


def _generate_player(
    rng: random.Random,
    strength: float,
    position: str,
    number: int,
    used_names: set[str],
) -> tuple:
    base = 62 + strength * 28
    pos_boost = {"GK": -2, "CB": 0, "LB": -1, "RB": -1, "CDM": 1, "CM": 0, "CAM": 2, "LW": 2, "RW": 2, "ST": 3}
    fc26 = max(58, min(92, round(base + pos_boost.get(position, 0) + rng.uniform(-4, 4))))
    value = max(0.3, (fc26 / 90) ** 4 * 120 * rng.uniform(0.4, 1.6))
    s2526 = max(5.5, min(8.5, 5.8 + strength * 2.2 + rng.uniform(-0.4, 0.4)))
    s2425 = s2526 + rng.uniform(-0.3, 0.3)
    s2324 = s2425 + rng.uniform(-0.3, 0.3)
    for _ in range(50):
        name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
        if name not in used_names:
            used_names.add(name)
            break
    return (name, position, number, fc26, round(value, 2), round(s2526, 1), round(s2425, 1), round(s2324, 1))


def _build_squad(fifa_code: str, fifa_rank: int) -> list[tuple]:
    rng = _rng(fifa_code)
    strength = _team_strength(fifa_rank)
    used_names: set[str] = set()
    curated = {entry[2]: entry for entry in CURATED.get(fifa_code, [])}
    squad: list[tuple] = []
    for position, number in POSITION_SLOTS:
        if number in curated:
            entry = curated[number]
            used_names.add(entry[0])
            squad.append(entry)
        else:
            squad.append(_generate_player(rng, strength, position, number, used_names))
    for entry in CURATED.get(fifa_code, []):
        if entry[2] not in {row[2] for row in squad}:
            squad.append(entry)
    squad.sort(key=lambda row: row[2])
    return squad[:SQUAD_SIZE]


def _generate_injuries(fifa_code: str, squad: list[tuple]) -> list[tuple]:
    rng = _rng(fifa_code + "-injuries")
    injuries: list[tuple] = []
    reference = date(2026, 6, 11)
    for name, *_ in squad:
        if rng.random() > 0.22:
            continue
        days_out = rng.choice([7, 10, 14, 21, 28, 35, 42, 56, 70, 90])
        if days_out < 14 and rng.random() > 0.3:
            continue
        ended_days_ago = rng.randint(5, 330)
        ended = reference - timedelta(days=ended_days_ago)
        started = ended - timedelta(days=days_out)
        injuries.append((fifa_code, name, started.isoformat(), ended.isoformat(), days_out))
    return injuries


def main() -> None:
    ranks = _load_ratings()
    teams = _load_teams()
    squad_rows: list[dict] = []
    injury_rows: list[dict] = []
    for fifa_code in teams:
        rank = ranks.get(fifa_code, 40)
        squad = _build_squad(fifa_code, rank)
        for name, position, number, fc26, value, s2526, s2425, s2324 in squad:
            squad_rows.append({
                "fifa_code": fifa_code,
                "name": name,
                "position": position,
                "squad_number": number,
                "fc26_overall": fc26,
                "market_value_meur": value,
                "season_rating_2025_26": s2526,
                "season_rating_2024_25": s2425,
                "season_rating_2023_24": s2324,
            })
        for row in _generate_injuries(fifa_code, squad):
            injury_rows.append({
                "fifa_code": row[0],
                "player_name": row[1],
                "started_on": row[2],
                "ended_on": row[3],
                "days_out": row[4],
            })

    squad_path = SEED_DIR / "squad.csv"
    injury_path = SEED_DIR / "player_injuries.csv"
    squad_fields = [
        "fifa_code", "name", "position", "squad_number", "fc26_overall", "market_value_meur",
        "season_rating_2025_26", "season_rating_2024_25", "season_rating_2023_24",
    ]
    with squad_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=squad_fields)
        writer.writeheader()
        writer.writerows(squad_rows)
    injury_fields = ["fifa_code", "player_name", "started_on", "ended_on", "days_out"]
    with injury_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=injury_fields)
        writer.writeheader()
        writer.writerows(injury_rows)
    print(f"Wrote {len(squad_rows)} players to {squad_path}")
    print(f"Wrote {len(injury_rows)} injuries to {injury_path}")


if __name__ == "__main__":
    main()
