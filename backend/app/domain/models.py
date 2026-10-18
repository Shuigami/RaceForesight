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


class ActualDriverStrategy(BaseModel):
    """Ground-truth tyre plan from OpenF1 race stints (no model race time)."""

    driver_number: int
    stops: int
    compounds: list[str]
    pit_laps: list[int]
    stints: list[StintPlan]
    strategy_label: str


class StrategyResponse(BaseModel):
    meeting: MeetingSummary
    drivers: list[DriverStrategy]
    actual: list[ActualDriverStrategy] = Field(default_factory=list)
    model_version: str = "xgboost-lap-v2"
    generated_at: str


class PacePoint(BaseModel):
    lap_number: int
    tyre_age: int
    fuel_proxy: int
    predicted_lap_s: float
    tyre_effect_s: float
    tyre_degradation_pct: float
    tyre_life_used_pct: float
    compound: str


class StintPaceCurve(BaseModel):
    stint_index: int
    compound: str
    lap_start: int
    lap_end: int
    points: list[PacePoint] = Field(default_factory=list)


class StrategyOption(BaseModel):
    strategy: DriverStrategy
    stint_curves: list[StintPaceCurve] = Field(default_factory=list)
    is_recommended: bool = False


class StrategyDetail(BaseModel):
    meeting: MeetingSummary
    best: DriverStrategy
    alternatives: list[DriverStrategy] = Field(default_factory=list)
    # Kept for backward compatibility: first stint race-pace points
    degradation_curve: list[dict] = Field(default_factory=list)
    stint_curves: list[StintPaceCurve] = Field(default_factory=list)
    # Recommended first, then alternatives — used by interactive detail UI
    options: list[StrategyOption] = Field(default_factory=list)
    actual: ActualDriverStrategy | None = None
    model_version: str = "xgboost-lap-v2"


class PredictedFinish(BaseModel):
    position: int
    driver_number: int
    name_acronym: str
    full_name: str
    team_name: str
    team_colour: str | None = None
    estimated_race_time_s: float | None = None
    gap_to_leader_s: float | None = None
    strategy_label: str | None = None
    confidence: float | None = None


class ClassificationResponse(BaseModel):
    meeting: MeetingSummary
    standings: list[PredictedFinish]
    model_version: str = "ranking-pairwise-v1"
    generated_at: str
    note: str = (
        "Finishing order from pairwise ranker (grid + form + pace), "
        "not Strategy tyre optimisation. Estimated times are secondary."
    )


class ModelScore(BaseModel):
    name: str
    kind: str
    version: str
    primary: bool = False
    metrics: dict[str, float | int | str | None]
    description: str = ""


class ModelsMetricsResponse(BaseModel):
    generated_at: str
    models: list[ModelScore]
    evaluation_races: int = 0
    notes: list[str] = Field(default_factory=list)
