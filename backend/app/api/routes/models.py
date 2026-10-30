from __future__ import annotations

import json
from functools import lru_cache

from fastapi import APIRouter, HTTPException, Query

from app.domain.models import (
    LiveModelArtifact,
    LiveModelsResponse,
    ModelsMetricsResponse,
    TrainJobRequest,
    TrainJobStatus,
    TrainModelProgress,
)
from app.evaluation.metrics import ModelEvaluator
from app.models.lap_time import LapTimeModel
from app.models.race_time import RaceTimeModel
from app.models.ranking import RankingModel
from app.training.jobs import train_jobs
from app.training.runners import TRAIN_TARGETS

router = APIRouter(prefix="/api/models", tags=["models"])


@lru_cache(maxsize=1)
def _evaluator() -> ModelEvaluator:
    return ModelEvaluator()


def _live_artifact(kind: str, model: LapTimeModel | RankingModel | RaceTimeModel) -> LiveModelArtifact:
    meta_path = model.artifact_dir / model.META_FILE
    if meta_path.exists():
        try:
            model.meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            model.meta = {}
    return LiveModelArtifact(
        kind=kind,
        name=model.DISPLAY_NAME,
        version=str(model.meta.get("version") or model.VERSION),
        ready=model.is_ready,
        trained_at=model.trained_at,
    )


def _job_to_status(raw: dict) -> TrainJobStatus:
    models = {
        key: TrainModelProgress.model_validate(val)
        for key, val in (raw.get("models") or {}).items()
    }
    return TrainJobStatus(
        job_id=str(raw["job_id"]),
        status=str(raw["status"]),
        targets=list(raw.get("targets") or []),
        years=list(raw.get("years") or []),
        max_sessions=raw.get("max_sessions"),
        started_at=raw.get("started_at"),
        finished_at=raw.get("finished_at"),
        error=raw.get("error"),
        models=models,
    )


@router.get("/artifacts", response_model=LiveModelsResponse)
def live_artifacts() -> LiveModelsResponse:
    """Live on-disk model versions + last train time (no evaluate required)."""
    return LiveModelsResponse(
        models={
            "lap_time": _live_artifact("lap_time", LapTimeModel()),
            "classification": _live_artifact("classification", RankingModel()),
            "race_time": _live_artifact("race_time", RaceTimeModel()),
        }
    )


@router.get("/metrics", response_model=ModelsMetricsResponse)
def get_metrics() -> ModelsMetricsResponse:
    cached = _evaluator().load()
    if cached is None:
        raise HTTPException(
            status_code=503,
            detail="No metrics artifact yet. Run: python scripts/evaluate_models.py",
        )
    return cached


@router.post("/evaluate", response_model=ModelsMetricsResponse)
def run_evaluation(
    years: str = Query(default="2023,2024,2025,2026"),
    max_sessions: int = Query(default=60, ge=3, le=100),
    ranking_races: int = Query(default=8, ge=1, le=15),
) -> ModelsMetricsResponse:
    year_list = [int(y.strip()) for y in years.split(",") if y.strip()]
    try:
        # Clear cached evaluator so next GET sees fresh instance state if needed
        _evaluator.cache_clear()
        evaluator = ModelEvaluator()
        try:
            return evaluator.evaluate(
                years=year_list,
                max_sessions=max_sessions,
                ranking_races=ranking_races,
            )
        finally:
            evaluator.close()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/train/status", response_model=TrainJobStatus | None)
def train_status() -> TrainJobStatus | None:
    raw = train_jobs.status()
    if raw is None:
        return None
    return _job_to_status(raw)


@router.post("/train", response_model=TrainJobStatus)
def start_train(body: TrainJobRequest | None = None) -> TrainJobStatus:
    body = body or TrainJobRequest()
    targets = body.targets or list(TRAIN_TARGETS)
    unknown = [t for t in targets if t not in TRAIN_TARGETS]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown targets {unknown}; allowed: {list(TRAIN_TARGETS)}",
        )
    years = None
    if body.years:
        years = [int(y.strip()) for y in body.years.split(",") if y.strip()]
    try:
        raw = train_jobs.start(targets, years=years, max_sessions=body.max_sessions)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _job_to_status(raw)
