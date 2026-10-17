from __future__ import annotations

from pydantic import BaseModel, Field


class MeetingSummary(BaseModel):
    meeting_key: int
    meeting_name: str
    circuit_short_name: str
    country_name: str
    year: int
    date_start: str | None = None
    is_default: bool = False
    race_laps: int = 56


class StintPlan(BaseModel):
    compound: str
    lap_start: int
    lap_end: int
    tyre_age_at_start: int = 0


class PitWindow(BaseModel):
    lap: int
    compound_in: str
    compound_out: str


class DriverStrategy(BaseModel):
    driver_number: int
    name_acronym: str
    full_name: str
    team_name: str
    team_colour: str | None = None
    stops: int
    compounds: list[str]
    pit_laps: list[int]
    stints: list[StintPlan]
    predicted_race_time_s: float
    predicted_avg_lap_s: float | None = None
    strategy_label: str


class StrategyResponse(BaseModel):
    meeting: MeetingSummary
    drivers: list[DriverStrategy]
    model_version: str = "xgboost-lap-v1"
    generated_at: str


class StrategyDetail(BaseModel):
    meeting: MeetingSummary
    best: DriverStrategy
    alternatives: list[DriverStrategy] = Field(default_factory=list)
    degradation_curve: list[dict] = Field(default_factory=list)
    model_version: str = "xgboost-lap-v1"
