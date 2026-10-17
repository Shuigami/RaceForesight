from functools import lru_cache

from fastapi import APIRouter, HTTPException, Query

from app.domain.models import ModelsMetricsResponse
from app.evaluation.metrics import ModelEvaluator

router = APIRouter(prefix="/api/models", tags=["models"])


@lru_cache(maxsize=1)
def _evaluator() -> ModelEvaluator:
    return ModelEvaluator()


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
    years: str = Query(default="2025,2026"),
    max_sessions: int = Query(default=40, ge=3, le=60),
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
