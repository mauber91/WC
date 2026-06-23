from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from world_cup_api.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Tournament(Base):
    __tablename__ = "tournaments"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    year: Mapped[int] = mapped_column(Integer, index=True)
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[date] = mapped_column(Date)
    ruleset_version: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Team(Base):
    __tablename__ = "teams"
    id: Mapped[int] = mapped_column(primary_key=True)
    fifa_code: Mapped[str] = mapped_column(String(3), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    short_name: Mapped[str] = mapped_column(String(40))
    country_code: Mapped[str] = mapped_column(String(2))
    confederation: Mapped[str] = mapped_column(String(12))
    flag_asset_uri: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Group(Base):
    __tablename__ = "groups"
    __table_args__ = (
        UniqueConstraint("tournament_id", "code"),
        UniqueConstraint("tournament_id", "sort_order"),
        Index("ix_groups_tournament_sort", "tournament_id", "sort_order"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(1))
    display_name: Mapped[str] = mapped_column(String(32))
    sort_order: Mapped[int] = mapped_column(Integer)
    tournament: Mapped[Tournament] = relationship()


class TournamentTeam(Base):
    __tablename__ = "tournament_teams"
    __table_args__ = (
        UniqueConstraint("tournament_id", "team_id"),
        UniqueConstraint("group_id", "draw_position"),
        Index("ix_tournament_teams_group", "group_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"))
    draw_position: Mapped[int] = mapped_column(Integer)
    is_host: Mapped[bool] = mapped_column(Boolean, default=False)
    team: Mapped[Team] = relationship()
    group: Mapped[Group] = relationship()


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (
        UniqueConstraint("tournament_id", "official_match_number"),
        CheckConstraint("team_a_id IS NULL OR team_b_id IS NULL OR team_a_id != team_b_id"),
        Index("ix_matches_tournament_stage", "tournament_id", "stage"),
        Index("ix_matches_status_scheduled", "status", "scheduled_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"))
    official_match_number: Mapped[int] = mapped_column(Integer)
    stage: Mapped[str] = mapped_column(String(24))
    group_id: Mapped[int | None] = mapped_column(ForeignKey("groups.id"), index=True)
    team_a_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), index=True)
    team_b_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), index=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    venue: Mapped[str] = mapped_column(String(120), default="TBD")
    host_country: Mapped[str] = mapped_column(String(2), default="US")
    status: Mapped[str] = mapped_column(String(20), default="scheduled")
    external_id: Mapped[str | None] = mapped_column(String(100))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    team_a: Mapped[Team | None] = relationship(foreign_keys=[team_a_id])
    team_b: Mapped[Team | None] = relationship(foreign_keys=[team_b_id])
    group: Mapped[Group | None] = relationship()


class MatchResult(Base):
    __tablename__ = "match_results"
    __table_args__ = (
        UniqueConstraint("match_id", "revision"),
        CheckConstraint("team_a_goals_90 >= 0 AND team_b_goals_90 >= 0"),
        Index("ux_match_results_current", "match_id", unique=True, sqlite_where=text("is_current = 1")),
        Index("ix_match_results_match_current", "match_id", "is_current"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"))
    revision: Mapped[int] = mapped_column(Integer)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    team_a_goals_90: Mapped[int] = mapped_column(Integer)
    team_b_goals_90: Mapped[int] = mapped_column(Integer)
    team_a_extra_time_goals: Mapped[int | None] = mapped_column(Integer)
    team_b_extra_time_goals: Mapped[int | None] = mapped_column(Integer)
    team_a_penalties: Mapped[int | None] = mapped_column(Integer)
    team_b_penalties: Mapped[int | None] = mapped_column(Integer)
    winner_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"))
    team_a_yellows: Mapped[int | None] = mapped_column(Integer)
    team_b_yellows: Mapped[int | None] = mapped_column(Integer)
    team_a_indirect_reds: Mapped[int | None] = mapped_column(Integer)
    team_b_indirect_reds: Mapped[int | None] = mapped_column(Integer)
    team_a_direct_reds: Mapped[int | None] = mapped_column(Integer)
    team_b_direct_reds: Mapped[int | None] = mapped_column(Integer)
    team_a_yellow_direct_reds: Mapped[int | None] = mapped_column(Integer)
    team_b_yellow_direct_reds: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(60), default="manual")
    source_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    match: Mapped[Match] = relationship()

    @property
    def conduct_a(self) -> int | None:
        return _conduct(self.team_a_yellows, self.team_a_indirect_reds, self.team_a_direct_reds, self.team_a_yellow_direct_reds)

    @property
    def conduct_b(self) -> int | None:
        return _conduct(self.team_b_yellows, self.team_b_indirect_reds, self.team_b_direct_reds, self.team_b_yellow_direct_reds)

    @property
    def red_cards_a(self) -> int:
        return _red_cards(self.team_a_indirect_reds, self.team_a_direct_reds, self.team_a_yellow_direct_reds)

    @property
    def red_cards_b(self) -> int:
        return _red_cards(self.team_b_indirect_reds, self.team_b_direct_reds, self.team_b_yellow_direct_reds)


def _red_cards(indirect: int | None, direct: int | None, yellow_direct: int | None) -> int:
    return int(indirect or 0) + int(direct or 0) + int(yellow_direct or 0)


def _conduct(y: int | None, ir: int | None, dr: int | None, ydr: int | None) -> int | None:
    if any(value is None for value in (y, ir, dr, ydr)):
        return None
    return -(int(y) + 3 * int(ir) + 4 * int(dr) + 5 * int(ydr))


class TeamRating(Base):
    __tablename__ = "team_ratings"
    __table_args__ = (
        UniqueConstraint("team_id", "rating_type", "source", "effective_at"),
        Index("ix_ratings_team_type_effective", "team_id", "rating_type", "effective_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    rating_type: Mapped[str] = mapped_column(String(24))
    rating_value: Mapped[float] = mapped_column(Float)
    rank: Mapped[int | None] = mapped_column(Integer)
    attack_rating: Mapped[float | None] = mapped_column(Float)
    defense_rating: Mapped[float | None] = mapped_column(Float)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(60))
    source_ref: Mapped[str | None] = mapped_column(String(255))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SquadPlayer(Base):
    __tablename__ = "squad_players"
    __table_args__ = (
        UniqueConstraint("team_id", "squad_number"),
        Index("ix_squad_players_team", "team_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120))
    position: Mapped[str] = mapped_column(String(4))
    squad_number: Mapped[int] = mapped_column(Integer)
    fc26_overall: Mapped[int] = mapped_column(Integer)
    market_value_meur: Mapped[float] = mapped_column(Float)
    season_rating_2025_26: Mapped[float | None] = mapped_column(Float)
    season_rating_2024_25: Mapped[float | None] = mapped_column(Float)
    season_rating_2023_24: Mapped[float | None] = mapped_column(Float)
    team: Mapped[Team] = relationship()
    injuries: Mapped[list[PlayerInjury]] = relationship(back_populates="player", cascade="all, delete-orphan")


class PlayerInjury(Base):
    __tablename__ = "player_injuries"
    __table_args__ = (Index("ix_player_injuries_player", "player_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("squad_players.id", ondelete="CASCADE"))
    started_on: Mapped[date] = mapped_column(Date)
    ended_on: Mapped[date | None] = mapped_column(Date)
    days_out: Mapped[int] = mapped_column(Integer)
    player: Mapped[SquadPlayer] = relationship(back_populates="injuries")


class BookmakerOdds(Base):
    __tablename__ = "bookmaker_odds"
    __table_args__ = (
        UniqueConstraint("match_id", "bookmaker", "market_type", "selection", "line_value", "snapshot_at"),
        CheckConstraint("decimal_odds > 1"),
        Index("ix_odds_match_market_snapshot", "match_id", "market_type", "snapshot_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"))
    bookmaker: Mapped[str] = mapped_column(String(60))
    market_type: Mapped[str] = mapped_column(String(32))
    selection: Mapped[str] = mapped_column(String(32))
    line_value: Mapped[float] = mapped_column(Float, default=0)
    decimal_odds: Mapped[float] = mapped_column(Float)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    source_ref: Mapped[str | None] = mapped_column(String(255))


class PredictionMarketPrice(Base):
    __tablename__ = "prediction_market_prices"
    __table_args__ = (
        UniqueConstraint("platform", "contract_id", "selection", "snapshot_at"),
        CheckConstraint("yes_price >= 0 AND yes_price <= 1"),
        Index("ix_market_prices_match_snapshot", "match_id", "snapshot_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(32))
    external_market_id: Mapped[str] = mapped_column(String(120))
    contract_id: Mapped[str] = mapped_column(String(120))
    market_type: Mapped[str] = mapped_column(String(32))
    match_id: Mapped[int | None] = mapped_column(ForeignKey("matches.id"))
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"))
    selection: Mapped[str] = mapped_column(String(60))
    yes_price: Mapped[float] = mapped_column(Float)
    no_price: Mapped[float | None] = mapped_column(Float)
    best_bid: Mapped[float | None] = mapped_column(Float)
    best_ask: Mapped[float | None] = mapped_column(Float)
    volume: Mapped[float | None] = mapped_column(Float)
    liquidity: Mapped[float | None] = mapped_column(Float)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MatchPrediction(Base):
    __tablename__ = "match_predictions"
    __table_args__ = (
        UniqueConstraint("match_id", "model_version", "input_hash"),
        Index("ix_predictions_match_generated", "match_id", "generated_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    input_cutoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    input_hash: Mapped[str] = mapped_column(String(64))
    model_version: Mapped[str] = mapped_column(String(40))
    lambda_a: Mapped[float] = mapped_column(Float)
    lambda_b: Mapped[float] = mapped_column(Float)
    market_a: Mapped[float | None] = mapped_column(Float)
    market_draw: Mapped[float | None] = mapped_column(Float)
    market_b: Mapped[float | None] = mapped_column(Float)
    model_a: Mapped[float] = mapped_column(Float)
    model_draw: Mapped[float] = mapped_column(Float)
    model_b: Mapped[float] = mapped_column(Float)
    final_a: Mapped[float] = mapped_column(Float)
    final_draw: Mapped[float] = mapped_column(Float)
    final_b: Mapped[float] = mapped_column(Float)
    components_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    data_quality: Mapped[str] = mapped_column(String(20), default="complete")


class Simulation(Base):
    __tablename__ = "simulations"
    __table_args__ = (
        CheckConstraint("iterations IN (10000, 100000, 1000000)"),
        Index("ix_simulations_tournament_created", "tournament_id", "created_at"),
        Index("ix_simulations_input_hash", "input_hash"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id"))
    status: Mapped[str] = mapped_column(String(20), index=True)
    iterations: Mapped[int] = mapped_column(Integer)
    progress_iterations: Mapped[int] = mapped_column(Integer, default=0)
    seed: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    input_cutoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    input_hash: Mapped[str] = mapped_column(String(64))
    input_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    parameters_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    model_version: Mapped[str] = mapped_column(String(40), default="poisson-elo-fifa-market-v2")
    ruleset_version: Mapped[str] = mapped_column(String(64))
    engine_version: Mapped[str] = mapped_column(String(40), default="engine-v3")
    code_version: Mapped[str | None] = mapped_column(String(64))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    error_message: Mapped[str | None] = mapped_column(Text)


class SimulationTeamResult(Base):
    __tablename__ = "simulation_team_results"
    simulation_id: Mapped[str] = mapped_column(ForeignKey("simulations.id", ondelete="CASCADE"), primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), primary_key=True, index=True)
    finish_1_count: Mapped[int] = mapped_column(Integer, default=0)
    finish_2_count: Mapped[int] = mapped_column(Integer, default=0)
    finish_3_count: Mapped[int] = mapped_column(Integer, default=0)
    finish_4_count: Mapped[int] = mapped_column(Integer, default=0)
    advance_as_third_count: Mapped[int] = mapped_column(Integer, default=0)
    round_of_32_count: Mapped[int] = mapped_column(Integer, default=0)
    round_of_16_count: Mapped[int] = mapped_column(Integer, default=0)
    quarterfinal_count: Mapped[int] = mapped_column(Integer, default=0)
    semifinal_count: Mapped[int] = mapped_column(Integer, default=0)
    final_count: Mapped[int] = mapped_column(Integer, default=0)
    champion_count: Mapped[int] = mapped_column(Integer, default=0)
    sum_group_points: Mapped[float] = mapped_column(Float, default=0)
    sum_group_goals_for: Mapped[float] = mapped_column(Float, default=0)
    sum_group_goals_against: Mapped[float] = mapped_column(Float, default=0)


class SimulationGroupResult(Base):
    __tablename__ = "simulation_group_results"
    __table_args__ = (
        UniqueConstraint("simulation_id", "group_id", "rank_1_team_id", "rank_2_team_id", "rank_3_team_id", "rank_4_team_id"),
        Index("ix_sim_group_occurrence", "simulation_id", "group_id", "occurrence_count"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    simulation_id: Mapped[str] = mapped_column(ForeignKey("simulations.id", ondelete="CASCADE"))
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"))
    rank_1_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    rank_2_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    rank_3_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    rank_4_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    occurrence_count: Mapped[int] = mapped_column(Integer)


class SimulationBracketResult(Base):
    __tablename__ = "simulation_bracket_results"
    __table_args__ = (
        UniqueConstraint("simulation_id", "official_match_number", "team_a_id", "team_b_id"),
        Index("ix_sim_bracket_match", "simulation_id", "official_match_number", "meeting_count"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    simulation_id: Mapped[str] = mapped_column(ForeignKey("simulations.id", ondelete="CASCADE"))
    official_match_number: Mapped[int] = mapped_column(Integer)
    team_a_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    team_b_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    meeting_count: Mapped[int] = mapped_column(Integer)
    team_a_advance_count: Mapped[int] = mapped_column(Integer)


class SimulationTeamR32Rival(Base):
    __tablename__ = "simulation_team_r32_rivals"
    __table_args__ = (
        UniqueConstraint("simulation_id", "team_id", "finish_position", "opponent_team_id"),
        Index("ix_sim_team_r32_rival", "simulation_id", "team_id", "finish_position"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    simulation_id: Mapped[str] = mapped_column(ForeignKey("simulations.id", ondelete="CASCADE"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    finish_position: Mapped[int] = mapped_column(Integer)
    opponent_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    meeting_count: Mapped[int] = mapped_column(Integer)


class BracketSlot(Base):
    __tablename__ = "bracket_slots"
    __table_args__ = (UniqueConstraint("ruleset_version", "official_match_number"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    ruleset_version: Mapped[str] = mapped_column(String(64))
    official_match_number: Mapped[int] = mapped_column(Integer)
    stage: Mapped[str] = mapped_column(String(24))
    side_a_source_type: Mapped[str] = mapped_column(String(24))
    side_a_source_ref: Mapped[str] = mapped_column(String(32))
    side_b_source_type: Mapped[str] = mapped_column(String(24))
    side_b_source_ref: Mapped[str] = mapped_column(String(32))
    next_match_number: Mapped[int | None] = mapped_column(Integer)
    next_side: Mapped[str | None] = mapped_column(String(1))


class ThirdPlaceAssignment(Base):
    __tablename__ = "third_place_assignments"
    __table_args__ = (UniqueConstraint("ruleset_version", "qualified_group_set", "target_match_number"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    ruleset_version: Mapped[str] = mapped_column(String(64))
    qualified_group_set: Mapped[str] = mapped_column(String(12))
    target_match_number: Mapped[int] = mapped_column(Integer)
    third_place_group_code: Mapped[str] = mapped_column(String(1))


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    __table_args__ = (Index("ix_ingestion_dataset_completed", "dataset_type", "completed_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dataset_type: Mapped[str] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(20), index=True)
    checksum: Mapped[str] = mapped_column(String(64))
    staged_path: Mapped[str | None] = mapped_column(String(255))
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, default=0)
    source_cutoff_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)


# Import the report models after the core models are defined. This registers the
# tables with Base.metadata for create_all and Alembic without crowding this file.
from world_cup_api.db import report_models as report_models  # noqa: E402,F401
