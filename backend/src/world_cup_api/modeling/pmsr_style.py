from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from statistics import mean, pstdev
from typing import TYPE_CHECKING, Any

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from world_cup_api.config import ROOT_DIR
from world_cup_api.db.models import Match, Team
from world_cup_api.db.report_models import (
    MatchReportDocument,
    MatchReportEvent,
    MatchReportExtractionRun,
    MatchReportNetworkEdge,
    MatchReportObservation,
    MatchReportSpatialFeature,
    MatchReportTimeseriesPoint,
)
from world_cup_api.modeling.pmsr_features import (
    MIN_CONFIDENCE,
    TeamMatchPmsrFeatures,
    _average,
    _extractor_side_team_ids,
    _resolve_match_team_id,
    index_features_by_match,
    load_team_match_features,
)

if TYPE_CHECKING:
    from world_cup_api.modeling.prediction import MatchForecast

STYLE_CONFIG_PATH = ROOT_DIR / "data" / "modeling" / "pmsr_style_model.json"

ATTACK_AXES = (
    "possession_tendency",
    "verticality",
    "final_third_presence",
    "width_crossing",
    "chance_quality",
    "chance_central",
    "build_up_structure",
    "pass_volume",
    "tempo_counter",
    "gk_build_up",
)

DEFEND_AXES = (
    "block_depth",
    "press_intensity",
    "press_height",
    "compactness",
    "disruption",
    "solidity",
    "aerial_second_balls",
    "gk_sweeping",
)

INTERACTIONS = (
    ("possession_low_block", "possession_tendency", "block_depth"),
    ("build_up_press", "build_up_structure", "press_intensity"),
    ("width_compact", "width_crossing", "compactness"),
    ("central_block", "chance_central", "block_depth"),
    ("counter_high_line", "tempo_counter", "press_height"),
    ("gk_press", "gk_build_up", "press_intensity"),
)

TARGETS = ("xg_a", "xg_b", "possession_a", "shots_a", "shots_b", "sot_a", "sot_b")


@dataclass(frozen=True)
class TeamMatchStyleFeatures:
    """Extended per-match team row with all style-relevant PMSR signals."""

    base: TeamMatchPmsrFeatures
    ball_progressions: float | None = None
    completed_line_breaks: float | None = None
    defensive_line_breaks: float | None = None
    forced_turnovers: float | None = None
    receptions_final_third: float | None = None
    second_balls: float | None = None
    total_distance: float | None = None
    zone4_sprint: float | None = None
    physical_sprints: float | None = None
    physical_high_speed_runs: float | None = None
    physical_top_speed: float | None = None
    line_team_length_m: float | None = None
    formation_centroid_x: float | None = None
    formation_width_m: float | None = None
    formation_depth_m: float | None = None
    formation_line_spacing_m: float | None = None
    extent_width_m: float | None = None
    extent_depth_m: float | None = None
    pressure_avg_x_m: float | None = None
    defensive_action_count: int = 0
    attempt_spatial_avg_x: float | None = None
    attempt_spatial_avg_y: float | None = None
    cross_avg_start_x: float | None = None
    gk_distribution_count: int = 0
    gk_distribution_avg_length_m: float | None = None
    offer_to_receive_count: int = 0
    movement_to_receive_count: int = 0
    card_count: int = 0
    network_passes: int = 0
    network_top_share: float | None = None
    gk_involvement_avg: float | None = None
    gk_involvement_std: float | None = None
    shots_total: float | None = None

    @property
    def match_id(self) -> int:
        return self.base.match_id

    @property
    def team_id(self) -> int:
        return self.base.team_id

    @property
    def official_match_number(self) -> int:
        return self.base.official_match_number


@dataclass(frozen=True)
class TeamStyleProfile:
    team_id: int
    matches_played: int
    attack: dict[str, float]
    defend: dict[str, float]

    def attack_axis(self, name: str) -> float:
        return self.attack.get(name, 0.5)

    def defend_axis(self, name: str) -> float:
        return self.defend.get(name, 0.5)

    def to_dict(self) -> dict[str, Any]:
        return {
            "team_id": self.team_id,
            "matches_played": self.matches_played,
            "attack": self.attack,
            "defend": self.defend,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TeamStyleProfile:
        return cls(
            team_id=int(data["team_id"]),
            matches_played=int(data["matches_played"]),
            attack=dict(data["attack"]),
            defend=dict(data["defend"]),
        )


def published_style_profiles_path() -> Path:
    """Sidecar cache written at publish time; lives next to the SQLite DB on Fly."""
    from world_cup_api.config import ROOT_DIR, get_settings

    settings = get_settings()
    if settings.database_url.startswith("sqlite:///"):
        db_path = Path(settings.database_url.removeprefix("sqlite:///"))
        return db_path.parent / "team_style_profiles.json"
    return ROOT_DIR / "data" / "app" / "team_style_profiles.json"


def build_all_team_style_profiles(session: Session) -> dict[int, TeamStyleProfile]:
    """Build lagged group-stage profiles for every team with PMSR coverage."""
    style_model = ensure_style_model(session)
    style_features = load_team_match_style_features(session)
    if not style_features:
        return {}
    style_by_match = index_style_features_by_match(style_features)
    bounds = style_model.percentile_bounds or compute_percentile_bounds(style_features)
    cutoff = session.scalar(select(func.max(Match.official_match_number)).where(Match.group_id.is_not(None)))
    before_match_number = int(cutoff or 72) + 1
    profiles: dict[int, TeamStyleProfile] = {}
    for team_id in {feature.team_id for feature in style_features}:
        profile = build_team_style_profile(
            style_features, style_by_match, team_id, before_match_number, bounds
        )
        if profile is not None:
            profiles[team_id] = profile
    return profiles


def save_published_style_profiles(profiles: dict[int, TeamStyleProfile], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {str(team_id): profile.to_dict() for team_id, profile in profiles.items()}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


@lru_cache
def load_published_style_profiles() -> dict[int, TeamStyleProfile]:
    path = published_style_profiles_path()
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {int(team_id): TeamStyleProfile.from_dict(data) for team_id, data in raw.items()}


def resolve_team_style_profile(
    style_features: list[TeamMatchStyleFeatures],
    style_by_match: dict[int, dict[int, TeamMatchStyleFeatures]],
    team_id: int,
    before_match_number: int,
    bounds: dict[str, tuple[float, float]],
) -> TeamStyleProfile | None:
    cached = load_published_style_profiles()
    if team_id in cached:
        return cached[team_id]
    return build_team_style_profile(style_features, style_by_match, team_id, before_match_number, bounds)


@dataclass(frozen=True)
class StyleInteractionScore:
    key: str
    label: str
    value: float
    coefficient: float
    contribution: float


@dataclass(frozen=True)
class StyleMatchup:
    favor: str
    net_xg_delta_a: float
    interactions: tuple[StyleInteractionScore, ...]
    narrative: str
    overall_favor: str = "even"


@dataclass(frozen=True)
class TacticalStats:
    possession_a: float
    possession_b: float
    shots_a: float
    shots_b: float
    sot_a: float
    sot_b: float
    xg_a: float
    xg_b: float


@dataclass
class StyleModelBundle:
    ridge_alpha: float = 1.0
    interaction_coefficients: dict[str, float] = field(default_factory=dict)
    target_models: dict[str, dict[str, Any]] = field(default_factory=dict)
    percentile_bounds: dict[str, tuple[float, float]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ridge_alpha": self.ridge_alpha,
            "interaction_coefficients": self.interaction_coefficients,
            "target_models": self.target_models,
            "percentile_bounds": self.percentile_bounds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StyleModelBundle:
        return cls(
            ridge_alpha=float(data.get("ridge_alpha", 1.0)),
            interaction_coefficients=dict(data.get("interaction_coefficients", {})),
            target_models=dict(data.get("target_models", {})),
            percentile_bounds={
                key: tuple(value) for key, value in data.get("percentile_bounds", {}).items()
            },
        )


def _percentile(value: float | None, bounds: dict[str, tuple[float, float]], key: str) -> float:
    if value is None:
        return 0.5
    low, high = bounds.get(key, (0.0, 1.0))
    if high <= low:
        return 0.5
    return float(np.clip((value - low) / (high - low), 0.0, 1.0))


def _resolve_team(run_id: str, team_id: int, document_by_run: dict, side_team_ids: dict[int, str]) -> int:
    document_row = document_by_run[run_id]
    assert document_row.team_a_id is not None and document_row.team_b_id is not None
    return _resolve_match_team_id(team_id, document_row.team_a_id, document_row.team_b_id, side_team_ids)


def load_team_match_style_features(session: Session) -> list[TeamMatchStyleFeatures]:
    """Load base features plus extended style signals from PMSR tables."""
    base_features = load_team_match_features(session)
    if not base_features:
        return []
    base_by_key = {(feature.match_id, feature.team_id): feature for feature in base_features}

    documents = session.execute(
        select(
            MatchReportDocument.match_id,
            MatchReportDocument.official_match_number,
            Match.team_a_id,
            Match.team_b_id,
            MatchReportExtractionRun.id,
        )
        .join(
            MatchReportExtractionRun,
            (MatchReportExtractionRun.document_id == MatchReportDocument.id)
            & MatchReportExtractionRun.is_active.is_(True),
        )
        .join(Match, Match.id == MatchReportDocument.match_id)
        .where(MatchReportDocument.match_id.is_not(None))
    ).all()
    document_by_run = {row.id: row for row in documents}
    run_ids = list(document_by_run)
    side_team_ids = _extractor_side_team_ids(session)

    extra_summary = {
        "summary.ball_progressions": "ball_progressions",
        "summary.completed_line_breaks": "completed_line_breaks",
        "summary.defensive_line_breaks": "defensive_line_breaks",
        "summary.forced_turnovers": "forced_turnovers",
        "summary.receptions_in_the_final_third": "receptions_final_third",
        "summary.second_balls": "second_balls",
        "summary.total_distance_covered": "total_distance",
        "summary.zone_4_low_speed_sprinting_20_25_km_h": "zone4_sprint",
        "spatial.line_or_team_length": "line_team_length_m",
    }
    obs_extra: dict[tuple[str, int], dict[str, float]] = defaultdict(dict)
    observations = session.scalars(
        select(MatchReportObservation).where(
            MatchReportObservation.run_id.in_(run_ids),
            MatchReportObservation.confidence >= MIN_CONFIDENCE,
            MatchReportObservation.team_id.is_not(None),
        )
    ).all()
    physical_keys = (
        "physical.sprints",
        "physical.high_speed_runs",
        "physical.top_speed",
    )
    physical_vals: dict[tuple[str, int], dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for observation in observations:
        assert observation.team_id is not None
        team_id = _resolve_team(observation.run_id, observation.team_id, document_by_run, side_team_ids)
        key = (observation.run_id, team_id)
        if observation.metric_key in extra_summary and observation.scope == "team":
            obs_extra[key][extra_summary[observation.metric_key]] = observation.value_numeric
        if observation.metric_key in physical_keys and observation.scope == "player":
            field_name = observation.metric_key.split(".", 1)[1]
            if observation.value_numeric is not None:
                physical_vals[key][field_name].append(observation.value_numeric)

    spatial_rows = session.scalars(
        select(MatchReportSpatialFeature).where(
            MatchReportSpatialFeature.run_id.in_(run_ids),
            MatchReportSpatialFeature.feature_type.in_(("formation_summary", "team_extent")),
        )
    ).all()
    spatial: dict[tuple[str, int], dict[str, float]] = defaultdict(dict)
    for row in spatial_rows:
        if row.team_id is None:
            continue
        team_id = _resolve_team(row.run_id, row.team_id, document_by_run, side_team_ids)
        key = (row.run_id, team_id)
        attrs = row.attributes_json or {}
        if row.feature_type == "formation_summary":
            for attr_key, field_name in (
                ("centroid_x_m", "formation_centroid_x"),
                ("width_m", "formation_width_m"),
                ("depth_m", "formation_depth_m"),
                ("mean_line_spacing_m", "formation_line_spacing_m"),
            ):
                if attr_key in attrs:
                    spatial[key][field_name] = float(attrs[attr_key])
        elif row.feature_type == "team_extent":
            if "width_m" in attrs:
                spatial[key]["extent_width_m"] = float(attrs["width_m"])
            if "depth_m" in attrs:
                spatial[key]["extent_depth_m"] = float(attrs["depth_m"])

    events = session.scalars(
        select(MatchReportEvent).where(
            MatchReportEvent.run_id.in_(run_ids),
            MatchReportEvent.team_id.is_not(None),
        )
    ).all()
    event_agg: dict[tuple[str, int], dict[str, Any]] = defaultdict(lambda: defaultdict(list))
    event_counts: dict[tuple[str, int], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for event in events:
        assert event.team_id is not None
        team_id = _resolve_team(event.run_id, event.team_id, document_by_run, side_team_ids)
        key = (event.run_id, team_id)
        event_counts[key][event.event_type] += 1
        if event.event_type == "pressure" and event.pitch_start_x_m is not None:
            event_agg[key]["pressure_x"].append(event.pitch_start_x_m)
        if event.event_type == "attempt_spatial":
            if event.pitch_start_x_m is not None:
                event_agg[key]["attempt_x"].append(event.pitch_start_x_m)
            if event.pitch_start_y_m is not None:
                event_agg[key]["attempt_y"].append(abs(event.pitch_start_y_m - 34.0))
        if event.event_type == "cross" and event.pitch_start_x_m is not None:
            event_agg[key]["cross_x"].append(event.pitch_start_x_m)
        if event.event_type == "goalkeeper_distribution" and event.length_m is not None:
            event_agg[key]["gk_len"].append(event.length_m)

    network_rows = session.scalars(
        select(MatchReportNetworkEdge).where(MatchReportNetworkEdge.run_id.in_(run_ids))
    ).all()
    network: dict[tuple[str, int], dict[str, float]] = defaultdict(dict)
    net_totals: dict[tuple[str, int], int] = defaultdict(int)
    net_max_share: dict[tuple[str, int], float] = defaultdict(float)
    for edge in network_rows:
        if edge.team_id is None:
            continue
        team_id = _resolve_team(edge.run_id, edge.team_id, document_by_run, side_team_ids)
        key = (edge.run_id, team_id)
        net_totals[key] += edge.pass_count
        if edge.pass_share is not None:
            net_max_share[key] = max(net_max_share[key], float(edge.pass_share))
    for key, total in net_totals.items():
        network[key]["network_passes"] = float(total)
        network[key]["network_top_share"] = net_max_share[key]

    ts_rows = session.scalars(
        select(MatchReportTimeseriesPoint).where(
            MatchReportTimeseriesPoint.run_id.in_(run_ids),
            MatchReportTimeseriesPoint.series_key == "goalkeeper.involvement",
        )
    ).all()
    ts_vals: dict[tuple[str, int], list[float]] = defaultdict(list)
    for row in ts_rows:
        if row.team_id is None:
            continue
        team_id = _resolve_team(row.run_id, row.team_id, document_by_run, side_team_ids)
        ts_vals[(row.run_id, team_id)].append(row.value)

    style_features: list[TeamMatchStyleFeatures] = []
    for row in documents:
        assert row.match_id is not None
        for team_id in (row.team_a_id, row.team_b_id):
            if team_id is None:
                continue
            base = base_by_key.get((row.match_id, team_id))
            if base is None:
                continue
            key = (row.id, team_id)
            phys = physical_vals.get(key, {})
            ev = event_agg.get(key, {})
            ec = event_counts.get(key, {})
            gk_values = ts_vals.get(key, [])
            kwargs: dict[str, Any] = {}
            kwargs.update(obs_extra.get(key, {}))
            kwargs.update(spatial.get(key, {}))
            kwargs.update(network.get(key, {}))
            kwargs["physical_sprints"] = _average(phys.get("sprints", []))
            kwargs["physical_high_speed_runs"] = _average(phys.get("high_speed_runs", []))
            kwargs["physical_top_speed"] = _average(phys.get("top_speed", []))
            kwargs["defensive_action_count"] = ec.get("defensive_action", 0)
            kwargs["gk_distribution_count"] = ec.get("goalkeeper_distribution", 0)
            kwargs["offer_to_receive_count"] = ec.get("offer_to_receive", 0)
            kwargs["movement_to_receive_count"] = ec.get("movement_to_receive", 0)
            kwargs["card_count"] = ec.get("card", 0)
            kwargs["pressure_avg_x_m"] = _average(ev.get("pressure_x", []))
            kwargs["attempt_spatial_avg_x"] = _average(ev.get("attempt_x", []))
            kwargs["attempt_spatial_avg_y"] = _average(ev.get("attempt_y", []))
            kwargs["cross_avg_start_x"] = _average(ev.get("cross_x", []))
            kwargs["gk_distribution_avg_length_m"] = _average(ev.get("gk_len", []))
            kwargs["gk_involvement_avg"] = _average(gk_values) if gk_values else None
            kwargs["gk_involvement_std"] = float(pstdev(gk_values)) if len(gk_values) > 1 else None
            on_target = float(base.shots_on_target or 0)
            # Total shots = all attempt events (on + off target); fall back to
            # spatial attempts, floored at shots on target. The PMSR summary has
            # no total-attempts field, so we derive it from attempt events.
            attempt_count = ec.get("attempt", 0) or base.attempt_spatial_count or ec.get("attempt_spatial", 0)
            kwargs["shots_total"] = max(on_target, float(attempt_count))
            style_features.append(TeamMatchStyleFeatures(base=base, **kwargs))
    return style_features


def _raw_style_values(feature: TeamMatchStyleFeatures) -> dict[str, float | None]:
    b = feature.base
    return {
        "possession": b.possession_pct,
        "xg": b.xg,
        "sot": b.shots_on_target,
        "shots": feature.shots_total,
        "ball_progressions": feature.ball_progressions,
        "completed_line_breaks": feature.completed_line_breaks,
        "defensive_line_breaks": feature.defensive_line_breaks,
        "forced_turnovers": feature.forced_turnovers,
        "receptions_final_third": feature.receptions_final_third,
        "crosses": b.crosses,
        "pass_completion": b.pass_completion_pct,
        "passes": b.passes_complete,
        "pressures": b.pressures,
        "second_balls": feature.second_balls,
        "zone4_sprint": feature.zone4_sprint,
        "physical_sprints": feature.physical_sprints,
        "line_length": feature.line_team_length_m,
        "formation_centroid_x": feature.formation_centroid_x,
        "formation_width": feature.formation_width_m,
        "formation_depth": feature.formation_depth_m,
        "formation_spacing": feature.formation_line_spacing_m,
        "pressure_avg_x": feature.pressure_avg_x_m,
        "defensive_actions": float(feature.defensive_action_count),
        "attempt_avg_x": feature.attempt_spatial_avg_x,
        "attempt_avg_y": feature.attempt_spatial_avg_y,
        "cross_avg_x": feature.cross_avg_start_x,
        "gk_dist_len": feature.gk_distribution_avg_length_m,
        "network_passes": float(feature.network_passes),
        "network_top_share": feature.network_top_share,
        "gk_involvement": feature.gk_involvement_avg,
    }


def compute_percentile_bounds(features: list[TeamMatchStyleFeatures]) -> dict[str, tuple[float, float]]:
    collected: dict[str, list[float]] = defaultdict(list)
    for feature in features:
        for key, value in _raw_style_values(feature).items():
            if value is not None:
                collected[key].append(float(value))
    bounds: dict[str, tuple[float, float]] = {}
    for key, values in collected.items():
        if values:
            bounds[key] = (float(min(values)), float(max(values)))
    return bounds


def _composite_attack(feature: TeamMatchStyleFeatures, bounds: dict[str, tuple[float, float]]) -> dict[str, float]:
    raw = _raw_style_values(feature)
    p = lambda k: _percentile(raw.get(k), bounds, k)
    verticality = 0.5 * (p("ball_progressions") + p("completed_line_breaks"))
    width_cross = 0.5 * (p("crosses") + p("cross_avg_x"))
    chance_central = 1.0 - p("attempt_avg_y") if raw.get("attempt_avg_y") is not None else 0.5
    build_up = 0.5 * (p("network_top_share") + p("pass_completion"))
    tempo = 0.5 * (p("physical_sprints") + p("zone4_sprint"))
    gk_build = 1.0 - p("gk_dist_len") if raw.get("gk_dist_len") is not None else 0.5
    return {
        "possession_tendency": p("possession"),
        "verticality": verticality,
        "final_third_presence": p("receptions_final_third"),
        "width_crossing": width_cross,
        "chance_quality": 0.5 * (p("xg") + p("sot")),
        "chance_central": chance_central,
        "build_up_structure": build_up,
        "pass_volume": 0.5 * (p("passes") + p("pass_completion")),
        "tempo_counter": tempo,
        "gk_build_up": gk_build,
    }


def _composite_defend(
    feature: TeamMatchStyleFeatures,
    opponent: TeamMatchStyleFeatures | None,
    bounds: dict[str, tuple[float, float]],
) -> dict[str, float]:
    raw = _raw_style_values(feature)
    opp = _raw_style_values(opponent) if opponent else {}
    p = lambda k: _percentile(raw.get(k), bounds, k)
    po = lambda k: _percentile(opp.get(k), bounds, k)
    line_a = p("line_length") if raw.get("line_length") is not None else 0.5
    line_b = 1.0 - p("formation_centroid_x") if raw.get("formation_centroid_x") is not None else 0.5
    line_signal = 0.5 * (line_a + line_b)
    if raw.get("formation_spacing") is not None:
        compact = 0.5 * ((1.0 - p("formation_width")) + (1.0 - p("formation_spacing")))
    else:
        compact = 0.5
    solidity = 1.0 - 0.5 * (po("xg") + po("sot")) if opponent else 0.5
    return {
        "block_depth": line_signal,
        "press_intensity": 0.5 * (p("pressures") + p("defensive_actions")),
        "press_height": p("pressure_avg_x"),
        "compactness": compact,
        "disruption": 0.5 * (p("defensive_line_breaks") + p("forced_turnovers")),
        "solidity": solidity,
        "aerial_second_balls": p("second_balls"),
        "gk_sweeping": p("gk_involvement"),
    }


def build_team_style_profile(
    style_features: list[TeamMatchStyleFeatures],
    by_match: dict[int, dict[int, TeamMatchStyleFeatures]],
    team_id: int,
    before_match_number: int,
    bounds: dict[str, tuple[float, float]],
) -> TeamStyleProfile | None:
    prior = [f for f in style_features if f.team_id == team_id and f.official_match_number < before_match_number]
    prior.sort(key=lambda item: item.official_match_number)
    if not prior:
        return None
    attacks: list[dict[str, float]] = []
    defends: list[dict[str, float]] = []
    for feature in prior:
        opponents = by_match.get(feature.match_id, {})
        opponent_id = next((tid for tid in opponents if tid != team_id), None)
        opponent = opponents.get(opponent_id) if opponent_id else None
        attacks.append(_composite_attack(feature, bounds))
        defends.append(_composite_defend(feature, opponent, bounds))
    attack = {key: float(mean([row[key] for row in attacks])) for key in ATTACK_AXES}
    defend = {key: float(mean([row[key] for row in defends])) for key in DEFEND_AXES}
    return TeamStyleProfile(team_id=team_id, matches_played=len(prior), attack=attack, defend=defend)


def interaction_features(
    attack_a: TeamStyleProfile,
    defend_a: TeamStyleProfile,
    attack_b: TeamStyleProfile,
    defend_b: TeamStyleProfile,
) -> dict[str, float]:
    out: dict[str, float] = {}
    for key, atk_axis, def_axis in INTERACTIONS:
        out[f"{key}_a"] = attack_a.attack_axis(atk_axis) * defend_b.defend_axis(def_axis)
        out[f"{key}_b"] = attack_b.attack_axis(atk_axis) * defend_a.defend_axis(def_axis)
    return out


def _feature_vector(
    lambda_a: float,
    lambda_b: float,
    profile_a: TeamStyleProfile | None,
    profile_b: TeamStyleProfile | None,
) -> np.ndarray:
    if profile_a is None or profile_b is None:
        zeros = np.zeros(len(ATTACK_AXES) * 2 + len(DEFEND_AXES) * 2 + len(INTERACTIONS) * 2 + 2)
        return np.concatenate(([lambda_a, lambda_b], zeros))
    parts = [lambda_a, lambda_b]
    parts.extend(profile_a.attack_axis(k) for k in ATTACK_AXES)
    parts.extend(profile_a.defend_axis(k) for k in DEFEND_AXES)
    parts.extend(profile_b.attack_axis(k) for k in ATTACK_AXES)
    parts.extend(profile_b.defend_axis(k) for k in DEFEND_AXES)
    interactions = interaction_features(profile_a, profile_a, profile_b, profile_b)
    for key, _, _ in INTERACTIONS:
        parts.append(interactions[f"{key}_a"])
        parts.append(interactions[f"{key}_b"])
    return np.array(parts, dtype=float)


def _default_interaction_coefficients() -> dict[str, float]:
    return {
        "possession_low_block_a": -0.35,
        "possession_low_block_b": -0.35,
        "build_up_press_a": -0.15,
        "build_up_press_b": -0.15,
        "width_compact_a": 0.05,
        "width_compact_b": 0.05,
        "central_block_a": -0.12,
        "central_block_b": -0.12,
        "counter_high_line_a": 0.18,
        "counter_high_line_b": 0.18,
        "gk_press_a": -0.1,
        "gk_press_b": -0.1,
    }


def save_style_model(bundle: StyleModelBundle) -> None:
    STYLE_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    STYLE_CONFIG_PATH.write_text(json.dumps(bundle.to_dict(), indent=2), encoding="utf-8")


def load_style_model() -> StyleModelBundle:
    if STYLE_CONFIG_PATH.exists():
        return StyleModelBundle.from_dict(json.loads(STYLE_CONFIG_PATH.read_text(encoding="utf-8")))
    return StyleModelBundle(interaction_coefficients=_default_interaction_coefficients())


@lru_cache(maxsize=1)
def _cached_style_model() -> StyleModelBundle:
    return load_style_model()


def fit_style_model(session: Session, *, ridge_alpha: float = 1.0) -> StyleModelBundle:
    """Fit ridge models on group-stage PMSR matches (lagged profiles, no leakage)."""
    from world_cup_api.services.tournament_elo import current_tournament_elos

    style_features = load_team_match_style_features(session)
    if not style_features:
        bundle = StyleModelBundle(ridge_alpha=ridge_alpha, interaction_coefficients=_default_interaction_coefficients())
        save_style_model(bundle)
        return bundle
    by_match: dict[int, dict[int, TeamMatchStyleFeatures]] = defaultdict(dict)
    for feature in style_features:
        by_match[feature.match_id][feature.team_id] = feature
    bounds = compute_percentile_bounds(style_features)
    matches = session.scalars(
        select(Match).where(Match.group_id.is_not(None)).order_by(Match.official_match_number)
    ).all()
    elos = current_tournament_elos(session, matches[0].tournament_id) if matches else {}

    rows_x: list[np.ndarray] = []
    targets: dict[str, list[float]] = {key: [] for key in TARGETS}
    for match in matches:
        if match.team_a_id is None or match.team_b_id is None:
            continue
        fa = by_match.get(match.id, {}).get(match.team_a_id)
        fb = by_match.get(match.id, {}).get(match.team_b_id)
        if fa is None or fb is None:
            continue
        pa = build_team_style_profile(style_features, by_match, match.team_a_id, match.official_match_number, bounds)
        pb = build_team_style_profile(style_features, by_match, match.team_b_id, match.official_match_number, bounds)
        if pa is None or pb is None:
            continue
        from world_cup_api.modeling.prediction import expected_goals

        elo_a = elos.get(match.team_a_id, 1500)
        elo_b = elos.get(match.team_b_id, 1500)
        la, lb = expected_goals(elo_a, elo_b)
        rows_x.append(_feature_vector(la, lb, pa, pb))
        targets["xg_a"].append(float(fa.base.xg or la))
        targets["xg_b"].append(float(fb.base.xg or lb))
        targets["possession_a"].append(float(fa.base.possession_pct or 50.0))
        targets["shots_a"].append(float(fa.shots_total or 0))
        targets["shots_b"].append(float(fb.shots_total or 0))
        # The PMSR "attempts_at_goal_on_target" field is actually total attempts
        # (values reach 30-35), so derive SOT as a realistic on-target fraction.
        targets["sot_a"].append(float(fa.shots_total or 0) * 0.33)
        targets["sot_b"].append(float(fb.shots_total or 0) * 0.33)

    if not rows_x:
        bundle = StyleModelBundle(ridge_alpha=ridge_alpha, interaction_coefficients=_default_interaction_coefficients(), percentile_bounds=bounds)
        save_style_model(bundle)
        return bundle

    x_matrix = np.vstack(rows_x)
    scaler = StandardScaler()
    x_scaled = scaler.fit_transform(x_matrix)
    defaults = _default_interaction_coefficients()
    target_models: dict[str, dict[str, Any]] = {}
    for target_name in TARGETS:
        model = Ridge(alpha=ridge_alpha)
        y = np.array(targets[target_name], dtype=float)
        if target_name in ("xg_a", "xg_b"):
            # Predict the residual on top of the Elo baseline so the model can only
            # nudge lambda, not replace it (prevents blowouts on out-of-distribution
            # knockout pairings).
            baseline_col = x_matrix[:, 0] if target_name == "xg_a" else x_matrix[:, 1]
            y = y - baseline_col
        model.fit(x_scaled, y)
        target_models[target_name] = {
            "coef": model.coef_.tolist(),
            "intercept": float(model.intercept_),
            "scaler_mean": scaler.mean_.tolist(),
            "scaler_scale": scaler.scale_.tolist(),
            "residual": target_name in ("xg_a", "xg_b"),
        }

    # Fit interaction coefficients on xG residual, then shrink toward sensible
    # priors — 42 rows cannot reliably sign 12 interaction terms on their own.
    xg_model = Ridge(alpha=ridge_alpha)
    y_residual = np.array(targets["xg_a"], dtype=float) - x_matrix[:, 0]
    interaction_cols = list(range(2 + len(ATTACK_AXES) * 2 + len(DEFEND_AXES) * 2, x_scaled.shape[1]))
    if interaction_cols:
        xg_model.fit(x_scaled[:, interaction_cols], y_residual)
        coef_map = {}
        shrink = 0.5
        for index, (key, _, _) in enumerate(INTERACTIONS):
            learned_a = float(xg_model.coef_[index * 2])
            learned_b = float(xg_model.coef_[index * 2 + 1])
            coef_map[f"{key}_a"] = shrink * learned_a + (1.0 - shrink) * defaults.get(f"{key}_a", 0.0)
            coef_map[f"{key}_b"] = shrink * learned_b + (1.0 - shrink) * defaults.get(f"{key}_b", 0.0)
    else:
        coef_map = dict(defaults)

    bundle = StyleModelBundle(
        ridge_alpha=ridge_alpha,
        interaction_coefficients=coef_map,
        target_models=target_models,
        percentile_bounds=bounds,
    )
    save_style_model(bundle)
    _cached_style_model.cache_clear()
    return bundle


def _predict_target(model_data: dict[str, Any], features: np.ndarray) -> float:
    mean = np.array(model_data["scaler_mean"], dtype=float)
    scale = np.array(model_data["scaler_scale"], dtype=float)
    scale = np.where(scale == 0, 1.0, scale)
    scaled = (features - mean) / scale
    coef = np.array(model_data["coef"], dtype=float)
    return float(np.dot(scaled, coef) + model_data["intercept"])


def predict_tactical_stats(
    lambda_a: float,
    lambda_b: float,
    profile_a: TeamStyleProfile | None,
    profile_b: TeamStyleProfile | None,
    *,
    model: StyleModelBundle | None = None,
) -> TacticalStats:
    """Predict per-team match stats.

    xG is the already-style-adjusted forecast lambda (passed in). The ridge
    target models are used only for possession/shots/SOT, clamped to sane
    ranges. xG is not predicted from the residual ridge here because ~42
    training rows extrapolate wildly on knockout pairings — style adjusts xG
    via the interpretable, clamped matchup delta in apply_style_to_forecast.
    """
    model = model or _cached_style_model()
    features = _feature_vector(lambda_a, lambda_b, profile_a, profile_b)
    if not model.target_models:
        return TacticalStats(
            possession_a=profile_a.attack_axis("possession_tendency") * 100 if profile_a else 50.0,
            possession_b=profile_b.attack_axis("possession_tendency") * 100 if profile_b else 50.0,
            shots_a=max(lambda_a * 3, 0),
            shots_b=max(lambda_b * 3, 0),
            sot_a=max(lambda_a * 1.2, 0),
            sot_b=max(lambda_b * 1.2, 0),
            xg_a=lambda_a,
            xg_b=lambda_b,
        )
    possession_a = float(np.clip(_predict_target(model.target_models["possession_a"], features), 30, 70))
    # Derive shot volume from the style-adjusted xG so it reconciles with the
    # forecast (a 1.5 xG team takes ~15 shots, not 18; a 1.15 xG team takes
    # ~11, not 4). The ridge shots/sot models extrapolate on knockout pairings;
    # anchoring to xG keeps the card internally consistent. Possession tilts
    # volume (dominant-ball sides take more, lower-quality shots).
    poss_factor_a = 1.0 + (possession_a - 50.0) / 100.0
    poss_factor_b = 1.0 + ((100.0 - possession_a) - 50.0) / 100.0
    shots_a = float(np.clip(lambda_a / 0.10 * poss_factor_a, 4.0, 22.0))
    shots_b = float(np.clip(lambda_b / 0.10 * poss_factor_b, 4.0, 22.0))
    sot_a = float(np.clip(lambda_a / 0.30, 1.0, shots_a * 0.7))
    sot_b = float(np.clip(lambda_b / 0.30, 1.0, shots_b * 0.7))
    return TacticalStats(
        possession_a=possession_a,
        possession_b=100.0 - possession_a,
        shots_a=shots_a,
        shots_b=shots_b,
        sot_a=sot_a,
        sot_b=sot_b,
        xg_a=lambda_a,
        xg_b=lambda_b,
    )


def _overall_favor(lambda_a: float, lambda_b: float, *, margin: float = 0.12) -> str:
    if lambda_a - lambda_b > margin:
        return "team_a"
    if lambda_b - lambda_a > margin:
        return "team_b"
    return "even"


def _tactical_insight_sentence(
    interactions: tuple[StyleInteractionScore, ...],
    team_a_name: str,
    team_b_name: str,
) -> str:
    if not interactions:
        return ""
    top = max(interactions, key=lambda item: abs(item.contribution))
    if abs(top.contribution) < 0.02:
        return ""
    if top.key == "possession_low_block_a" and top.contribution < 0:
        return (
            f" {team_a_name}'s possession game may struggle against "
            f"{team_b_name}'s low block ({top.contribution:+.2f} xG)."
        )
    if top.key == "possession_low_block_b" and top.contribution > 0:
        return (
            f" {team_b_name}'s possession game may struggle against "
            f"{team_a_name}'s low block ({-top.contribution:+.2f} xG)."
        )
    return f" Standout interaction: {top.label} ({top.contribution:+.2f} xG)."


def compose_style_narrative(
    team_a_name: str,
    team_b_name: str,
    lambda_a: float,
    lambda_b: float,
    style_favor: str,
    delta_a: float,
    interactions: tuple[StyleInteractionScore, ...],
) -> str:
    """Blend overall xG favorite with tactical style edge for the UI summary."""
    overall = _overall_favor(lambda_a, lambda_b)
    xg_summary = f"{lambda_a:.2f} vs {lambda_b:.2f} xG"
    if overall == "team_a":
        quality = f"{team_a_name} are favored overall ({xg_summary})"
    elif overall == "team_b":
        quality = f"{team_b_name} are favored overall ({xg_summary})"
    else:
        quality = f"The teams look evenly matched on quality ({xg_summary})"

    if style_favor == "team_a":
        tactical = f"{team_a_name}'s attacking style fits this matchup better ({delta_a:+.2f} xG edge)"
    elif style_favor == "team_b":
        tactical = f"{team_b_name}'s style fits this matchup better ({abs(delta_a):.2f} xG edge)"
    else:
        tactical = "tactical styles are evenly matched"

    insight = _tactical_insight_sentence(interactions, team_a_name, team_b_name)

    if overall == style_favor:
        if overall == "even":
            return f"{quality}, and {tactical}."
        return f"{quality}, and {tactical}—ratings and tactics point the same way.{insight}"

    if overall == "even":
        if style_favor == "even":
            return f"{quality}."
        return f"{quality}, but {tactical}.{insight}"

    overall_name = team_a_name if overall == "team_a" else team_b_name
    if style_favor == "even":
        return f"{quality}. Tactical styles are evenly matched—{overall_name} carry the quality edge.{insight}"

    tactical_name = team_a_name if style_favor == "team_a" else team_b_name
    return (
        f"{quality}, but {tactical_name}'s style fits better tactically "
        f"({abs(delta_a):.2f} xG style edge)—{overall_name} remain favored on overall strength.{insight}"
    )


def finalize_style_matchup(
    matchup: StyleMatchup,
    *,
    team_a_name: str,
    team_b_name: str,
    lambda_a: float,
    lambda_b: float,
) -> StyleMatchup:
    overall = _overall_favor(lambda_a, lambda_b)
    return StyleMatchup(
        favor=matchup.favor,
        net_xg_delta_a=matchup.net_xg_delta_a,
        interactions=matchup.interactions,
        narrative=compose_style_narrative(
            team_a_name,
            team_b_name,
            lambda_a,
            lambda_b,
            matchup.favor,
            matchup.net_xg_delta_a,
            matchup.interactions,
        ),
        overall_favor=overall,
    )


def score_style_matchup(
    profile_a: TeamStyleProfile,
    profile_b: TeamStyleProfile,
    *,
    team_a_name: str = "Team A",
    team_b_name: str = "Team B",
    model: StyleModelBundle | None = None,
    lambda_a: float | None = None,
    lambda_b: float | None = None,
) -> StyleMatchup:
    model = model or _cached_style_model()
    interactions = interaction_features(profile_a, profile_a, profile_b, profile_b)
    scores: list[StyleInteractionScore] = []
    delta_a = 0.0
    labels = {
        "possession_low_block": "possession vs low block",
        "build_up_press": "build-up vs press",
        "width_compact": "width vs compact block",
        "central_block": "central attack vs deep block",
        "counter_high_line": "counter vs high line",
        "gk_press": "GK build-up vs press",
    }
    for key, atk, defn in INTERACTIONS:
        value_a = interactions[f"{key}_a"]
        coef_a = model.interaction_coefficients.get(f"{key}_a", 0.0)
        contrib_a = coef_a * value_a
        delta_a += contrib_a
        scores.append(
            StyleInteractionScore(
                key=f"{key}_a",
                label=f"{team_a_name} {labels[key]}",
                value=round(value_a, 3),
                coefficient=coef_a,
                contribution=round(contrib_a, 3),
            )
        )
        value_b = interactions[f"{key}_b"]
        coef_b = model.interaction_coefficients.get(f"{key}_b", 0.0)
        contrib_b = coef_b * value_b
        delta_a -= contrib_b
        scores.append(
            StyleInteractionScore(
                key=f"{key}_b",
                label=f"{team_b_name} {labels[key]}",
                value=round(value_b, 3),
                coefficient=coef_b,
                contribution=round(-contrib_b, 3),
            )
        )
    # Style can only nudge xG, not drive it — clamp the net tactical edge.
    delta_a = float(np.clip(delta_a, -0.2, 0.2))
    if delta_a > 0.05:
        favor = "team_a"
    elif delta_a < -0.05:
        favor = "team_b"
    else:
        favor = "even"
    interaction_tuple = tuple(scores)
    if lambda_a is not None and lambda_b is not None:
        narrative = compose_style_narrative(
            team_a_name, team_b_name, lambda_a, lambda_b, favor, delta_a, interaction_tuple
        )
        overall = _overall_favor(lambda_a, lambda_b)
    else:
        narrative = "Tactical style breakdown available."
        overall = "even"
    return StyleMatchup(
        favor=favor,
        net_xg_delta_a=round(delta_a, 3),
        interactions=interaction_tuple,
        narrative=narrative,
        overall_favor=overall,
    )


def apply_style_to_forecast(
    forecast: MatchForecast,
    profile_a: TeamStyleProfile | None,
    profile_b: TeamStyleProfile | None,
    *,
    goal_dispersion: float = 0.0,
    market_blend_alpha: float = 0.0,
    model: StyleModelBundle | None = None,
    team_a_name: str = "Team A",
    team_b_name: str = "Team B",
) -> tuple[MatchForecast, TacticalStats, StyleMatchup | None]:
    from world_cup_api.modeling.prediction import MatchForecast, blend, one_x_two, reweight_score_matrix, score_matrix

    model = model or _cached_style_model()
    matchup = (
        score_style_matchup(profile_a, profile_b, team_a_name=team_a_name, team_b_name=team_b_name, model=model)
        if profile_a and profile_b
        else None
    )
    # Style adjusts xG only via the interpretable, clamped matchup delta — never
    # via the extrapolating residual ridge model. This keeps the forecast
    # anchored to the Elo baseline (which tracks the market) and the xG display
    # consistent with the narrative edge.
    delta = matchup.net_xg_delta_a if matchup is not None else 0.0
    lambda_a = float(np.clip(forecast.lambda_a + delta, 0.15, 3.0))
    lambda_b = float(np.clip(forecast.lambda_b - delta, 0.15, 3.0))
    tactical = predict_tactical_stats(lambda_a, lambda_b, profile_a, profile_b, model=model)
    if matchup is not None:
        matchup = finalize_style_matchup(
            matchup,
            team_a_name=team_a_name,
            team_b_name=team_b_name,
            lambda_a=lambda_a,
            lambda_b=lambda_b,
        )
    if lambda_a == forecast.lambda_a and lambda_b == forecast.lambda_b:
        return forecast, tactical, matchup
    raw_matrix = score_matrix(lambda_a, lambda_b, goal_dispersion=goal_dispersion)
    model_probs = one_x_two(raw_matrix)
    final = blend(model_probs, forecast.market, alpha=market_blend_alpha)
    matrix = reweight_score_matrix(raw_matrix, final)
    updated = MatchForecast(
        lambda_a,
        lambda_b,
        model_probs,
        forecast.market,
        final,
        tuple(tuple(float(value) for value in row) for row in matrix),
    )
    return updated, tactical, matchup


def index_style_features_by_match(
    features: list[TeamMatchStyleFeatures],
) -> dict[int, dict[int, TeamMatchStyleFeatures]]:
    indexed: dict[int, dict[int, TeamMatchStyleFeatures]] = defaultdict(dict)
    for feature in features:
        indexed[feature.match_id][feature.team_id] = feature
    return dict(indexed)


def ensure_style_model(session: Session) -> StyleModelBundle:
    if not STYLE_CONFIG_PATH.exists():
        return fit_style_model(session)
    return load_style_model()
