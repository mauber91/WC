from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ResultInput(BaseModel):
    team_a_goals_90: int = Field(ge=0)
    team_b_goals_90: int = Field(ge=0)
    team_a_extra_time_goals: int | None = Field(default=None, ge=0)
    team_b_extra_time_goals: int | None = Field(default=None, ge=0)
    team_a_penalties: int | None = Field(default=None, ge=0)
    team_b_penalties: int | None = Field(default=None, ge=0)
    winner_team_id: int | None = None
    team_a_yellows: int | None = Field(default=None, ge=0)
    team_b_yellows: int | None = Field(default=None, ge=0)
    team_a_indirect_reds: int | None = Field(default=None, ge=0)
    team_b_indirect_reds: int | None = Field(default=None, ge=0)
    team_a_direct_reds: int | None = Field(default=None, ge=0)
    team_b_direct_reds: int | None = Field(default=None, ge=0)
    team_a_yellow_direct_reds: int | None = Field(default=None, ge=0)
    team_b_yellow_direct_reds: int | None = Field(default=None, ge=0)
    source: str = "manual"
    source_updated_at: datetime | None = None


class SimulationInput(BaseModel):
    iterations: Literal[10_000, 100_000, 1_000_000] = 10_000
    seed: int = Field(default=2026, ge=0, le=2**63 - 1)
    force: bool = False


class SimulationStatus(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    status: str
    iterations: int
    progress_iterations: int
    seed: int
    input_cutoff_at: datetime
    model_version: str
    ruleset_version: str
    engine_version: str
    duration_ms: int | None
    error_message: str | None


class ProbabilityTriple(BaseModel):
    team_a: float
    draw: float
    team_b: float
