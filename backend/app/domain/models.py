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
    """Per-driver plan (detail endpoint / pace curves only)."""

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


class GlobalStrategy(BaseModel):
    """Race-level tyre plan — not tied to a driver."""

    rank: int
    stops: int
    compounds: list[str]
    pit_laps: list[int]
    stints: list[StintPlan]
    predicted_race_time_s: float
    predicted_avg_lap_s: float | None = None
    strategy_label: str
    gap_to_best_s: float


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
    strategies: list[GlobalStrategy]
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


class PredictionModelVersions(BaseModel):
    classification: str
    race_time: str
    strategy: str


class SavedClassificationSlice(BaseModel):
    standings: list[PredictedFinish]
    note: str = ""


class SavedStrategySlice(BaseModel):
    strategies: list[GlobalStrategy]


class PredictionSnapshot(BaseModel):
    meeting: MeetingSummary
    race_start_at: str | None = None
    first_saved_at: str
    saved_at: str
    model_versions: PredictionModelVersions
    classification: SavedClassificationSlice
    race_time: SavedClassificationSlice
    strategy: SavedStrategySlice


class PredictionListItem(BaseModel):
    meeting_key: int
    meeting_name: str
    year: int | None = None
    circuit_short_name: str | None = None
    first_saved_at: str | None = None
    saved_at: str | None = None
    race_start_at: str | None = None
    has_actual: bool = False
    lock_status: str
    status: str  # awaiting_race | scored


class ActualFinishRow(BaseModel):
    position: int
    driver_number: int
    duration_s: float | None = None


class PredictionCompareMetrics(BaseModel):
    classification: dict[str, float | int | None] = Field(default_factory=dict)
    race_time: dict[str, float | int | None] = Field(default_factory=dict)
    strategy: dict[str, float | int | None] = Field(default_factory=dict)


class PredictionCompareResponse(BaseModel):
    snapshot: PredictionSnapshot
    lock_status: str
    status: str
    overwritten: bool = False
    actual_finishes: list[ActualFinishRow] = Field(default_factory=list)
    actual_strategies: list[ActualDriverStrategy] = Field(default_factory=list)
    metrics: PredictionCompareMetrics | None = None
