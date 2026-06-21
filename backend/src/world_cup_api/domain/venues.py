from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from world_cup_api.config import ROOT_DIR

SEED_DIR = ROOT_DIR / "data" / "seed"


@dataclass(frozen=True)
class GeoPoint:
    lat: float
    lon: float


@dataclass(frozen=True)
class Venue:
    name: str
    city: str
    country: str
    lat: float
    lon: float
    altitude_m: float


def haversine_km(a: GeoPoint, b: GeoPoint) -> float:
    radius = 6371.0
    lat_a, lon_a = math.radians(a.lat), math.radians(a.lon)
    lat_b, lon_b = math.radians(b.lat), math.radians(b.lon)
    dlat = lat_b - lat_a
    dlon = lon_b - lon_a
    h = math.sin(dlat / 2) ** 2 + math.cos(lat_a) * math.cos(lat_b) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(h)))


@lru_cache
def venue_catalog() -> dict[str, Venue]:
    path = SEED_DIR / "venues.csv"
    venues: dict[str, Venue] = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            venues[row["venue_name"]] = Venue(
                name=row["venue_name"],
                city=row["city"],
                country=row["country"].upper(),
                lat=float(row["lat"]),
                lon=float(row["lon"]),
                altitude_m=float(row["altitude_m"]),
            )
    return venues


@lru_cache
def team_base_camps() -> dict[str, GeoPoint]:
    path = SEED_DIR / "team_base_camps.csv"
    camps: dict[str, GeoPoint] = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            camps[row["fifa_code"].upper()] = GeoPoint(float(row["lat"]), float(row["lon"]))
    return camps


def venue_point(venue_name: str) -> GeoPoint:
    venue = venue_catalog().get(venue_name)
    if venue is None:
        raise KeyError(f"Unknown venue: {venue_name}")
    return GeoPoint(venue.lat, venue.lon)


def base_camp_point(fifa_code: str) -> GeoPoint:
    camp = team_base_camps().get(fifa_code.upper())
    if camp is None:
        raise KeyError(f"Unknown team base camp: {fifa_code}")
    return camp


def travel_km_from_base(fifa_code: str, venue_name: str) -> float:
    return haversine_km(base_camp_point(fifa_code), venue_point(venue_name))
