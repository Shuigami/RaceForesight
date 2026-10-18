from functools import lru_cache

from fastapi import APIRouter, HTTPException, Query

from app.data.pipeline import RaceDataPipeline
from app.domain.models import (
    ClassificationResponse,
    MeetingSummary,
    StrategyDetail,
    StrategyResponse,
)
from app.simulation.prediction import ClassificationPredictor
from app.simulation.race_time import RaceTimePredictor
from app.simulation.strategy import StrategySimulator

router = APIRouter(prefix="/api", tags=["races"])


@lru_cache(maxsize=1)
def _pipeline() -> RaceDataPipeline:
    return RaceDataPipeline()


@lru_cache(maxsize=1)
def _simulator() -> StrategySimulator:
    return StrategySimulator(pipeline=_pipeline())


@lru_cache(maxsize=1)
def _predictor() -> ClassificationPredictor:
    return ClassificationPredictor(simulator=_simulator())


@lru_cache(maxsize=1)
def _race_time_predictor() -> RaceTimePredictor:
    return RaceTimePredictor(simulator=_simulator())


@router.get("/races", response_model=list[MeetingSummary])
def list_races(years: str | None = Query(default=None, description="Comma-separated years")) -> list[MeetingSummary]:
    year_list = None
    if years:
        year_list = [int(y.strip()) for y in years.split(",") if y.strip()]
    try:
        return _pipeline().list_meetings(year_list)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"OpenF1 error: {exc}") from exc


@router.get("/races/default", response_model=MeetingSummary)
def default_race() -> MeetingSummary:
    try:
        return _pipeline().get_meeting(None)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/races/{meeting_key}/strategy", response_model=StrategyResponse)
def race_strategy(meeting_key: int) -> StrategyResponse:
    try:
        key = None if meeting_key <= 0 else meeting_key
        return _simulator().simulate_grid(key)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/races/{meeting_key}/strategy/{driver_number}", response_model=StrategyDetail)
def driver_strategy(meeting_key: int, driver_number: int) -> StrategyDetail:
    try:
        key = None if meeting_key <= 0 else meeting_key
        return _simulator().simulate_driver_detail(key, driver_number)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/races/{meeting_key}/prediction", response_model=ClassificationResponse)
def race_prediction(meeting_key: int) -> ClassificationResponse:
    """Predicted finishing order — classification primary, times secondary."""
    try:
        key = None if meeting_key <= 0 else meeting_key
        return _predictor().predict(key)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/races/{meeting_key}/race-time", response_model=ClassificationResponse)
def race_time(meeting_key: int) -> ClassificationResponse:
    """Predicted race durations — dedicated race-time model (pace fallback if untrained)."""
    try:
        key = None if meeting_key <= 0 else meeting_key
        return _race_time_predictor().predict(key)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
