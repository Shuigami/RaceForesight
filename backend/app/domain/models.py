from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class MeetingSummary(BaseModel):
    meeting_key: int
    meeting_name: str
    circuit_short_name: str
    country_name: str
    year: int
    date_start: str | None = None
    is_default: bool = False
    race_laps: int = 56
    circuit_image: str | None = None
    country_flag: str | None = None


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
    """Race-level tyre plan — not tied to a driver.

    Same stop count + compounds collapse to one entry; pit_windows is the
    competitive lap range per stop (e.g. [[26, 30]] for a 1-stop S/H).
    pit_laps is the single fastest sample inside that window.
    """

    rank: int
    stops: int
    compounds: list[str]
    pit_laps: list[int]
    pit_windows: list[list[int]] = Field(default_factory=list)
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
    headshot_url: str | None = None
    estimated_race_time_s: float | None = None
    gap_to_leader_s: float | None = None
    strategy_label: str | None = None
    confidence: float | None = None


class ClassificationResponse(BaseModel):
    meeting: MeetingSummary
    standings: list[PredictedFinish]
    model_version: str = "ranking-pairwise-v2"
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


def infer_saved_model_name(section: str, version: str) -> str:
    """Best-effort display name when older saves only stored a version string."""
    v = (version or "").lower()
    if section == "classification" or "rank" in v:
        if "pace-grid" in v:
            return "Pace+grid heuristic"
        return "Classification (pairwise ranker)"
    if section == "race_time" or "race-time" in v:
        if "fallback" in v:
            return "Pace×distance fallback"
        return "Race time (XGBoost)"
    if "rf-lap" in v:
        return "Lap-time Random Forest"
    return "Lap-time XGBoost"


class SavedModelRef(BaseModel):
    name: str
    version: str
    trained_at: str | None = None


def _coerce_saved_model_ref(section: str, value: Any) -> Any:
    if isinstance(value, str):
        return {"name": infer_saved_model_name(section, value), "version": value, "trained_at": None}
    if isinstance(value, dict):
        version = str(value.get("version") or "")
        name = str(value.get("name") or "").strip()
        if not name and version:
            name = infer_saved_model_name(section, version)
        trained = value.get("trained_at")
        return {
            "name": name or infer_saved_model_name(section, version),
            "version": version,
            "trained_at": str(trained) if trained else None,
        }
    return value


class PredictionModelVersions(BaseModel):
    classification: SavedModelRef
    race_time: SavedModelRef
    strategy: SavedModelRef

    @field_validator("classification", "race_time", "strategy", mode="before")
    @classmethod
    def coerce_legacy_version_string(cls, value: Any, info) -> Any:
        return _coerce_saved_model_ref(str(info.field_name), value)


class SavedClassificationSlice(BaseModel):
    standings: list[PredictedFinish]
    note: str = ""


class SavedStrategySlice(BaseModel):
    strategies: list[GlobalStrategy]


class PredictionSnapshot(BaseModel):
    id: str = ""
    name: str = ""
    meeting: MeetingSummary
    race_start_at: str | None = None
    first_saved_at: str
    saved_at: str
    model_versions: PredictionModelVersions
    classification: SavedClassificationSlice
    race_time: SavedClassificationSlice
    strategy: SavedStrategySlice


class PredictionMeetingListItem(BaseModel):
    meeting_key: int
    meeting_name: str
    year: int | None = None
    circuit_short_name: str | None = None
    circuit_image: str | None = None
    country_flag: str | None = None
    first_saved_at: str | None = None
    saved_at: str | None = None
    race_start_at: str | None = None
    save_count: int = 0
    has_actual: bool = False
    status: str  # awaiting_race | scored


class PredictionSaveListItem(BaseModel):
    id: str
    name: str
    meeting_key: int
    meeting_name: str
    year: int | None = None
    circuit_short_name: str | None = None
    circuit_image: str | None = None
    country_flag: str | None = None
    first_saved_at: str | None = None
    saved_at: str | None = None
    race_start_at: str | None = None
    has_actual: bool = False
    lock_status: str
    integrity_status: str = "unknown"  # pre_race | post_race | train_overlap | awaiting_race | unknown
    status: str  # awaiting_race | scored
    model_versions: PredictionModelVersions | None = None


class PredictionSaveNameBody(BaseModel):
    name: str | None = None


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
    integrity_status: str = "unknown"
    status: str
    overwritten: bool = False
    actual_finishes: list[ActualFinishRow] = Field(default_factory=list)
    actual_strategies: list[ActualDriverStrategy] = Field(default_factory=list)
    metrics: PredictionCompareMetrics | None = None
