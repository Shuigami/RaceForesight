from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.api.routes.races import _pipeline, _predictor, _race_time_predictor, _simulator
from app.domain.models import (
    ActualFinishRow,
    PredictionCompareMetrics,
    PredictionCompareResponse,
    PredictionListItem,
    PredictionModelVersions,
    PredictionSnapshot,
    SavedClassificationSlice,
    SavedStrategySlice,
)
from app.predictions.compare import (
    classification_metrics,
    compute_lock_status,
    parse_actual_results,
    race_time_metrics,
    strategy_metrics,
)
from app.predictions.store import list_snapshots, load_snapshot, save_snapshot

router = APIRouter(prefix="/api/predictions", tags=["predictions"])


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _resolve_key(meeting_key: int) -> int:
    if meeting_key <= 0:
        return _pipeline().get_meeting(None).meeting_key
    return meeting_key


def _finishing_results(meeting_key: int) -> tuple[dict[int, int], dict[int, float]]:
    pipeline = _pipeline()
    session_key = pipeline.race_session_key(meeting_key)
    if not session_key:
        return {}, {}
    try:
        result = pipeline.client.session_result(session_key)
        positions, durations = parse_actual_results(result)
    except Exception:
        return {}, {}
    if len(positions) < 8:
        return {}, {}
    return positions, durations


def _load_actuals(meeting_key: int):
    positions, durations = _finishing_results(meeting_key)
    has_actual = bool(positions)
    actual_strategies = []
    if has_actual:
        try:
            actual_strategies = _pipeline().actual_strategies_for_meeting(meeting_key)
        except Exception:
            actual_strategies = []
    return has_actual, positions, durations, actual_strategies


def _enrich_list_item(raw: dict) -> PredictionListItem:
    mk = int(raw["meeting_key"])
    has_actual = bool(_finishing_results(mk)[0])
    lock = compute_lock_status(
        first_saved_at=raw.get("first_saved_at"),
        saved_at=raw.get("saved_at"),
        race_start_at=raw.get("race_start_at"),
    )
    return PredictionListItem(
        meeting_key=mk,
        meeting_name=str(raw.get("meeting_name") or mk),
        year=raw.get("year"),
        circuit_short_name=raw.get("circuit_short_name"),
        first_saved_at=raw.get("first_saved_at"),
        saved_at=raw.get("saved_at"),
        race_start_at=raw.get("race_start_at"),
        has_actual=has_actual,
        lock_status=lock,
        status="scored" if has_actual else "awaiting_race",
    )


@router.get("", response_model=list[PredictionListItem])
def list_saved_predictions() -> list[PredictionListItem]:
    return [_enrich_list_item(item) for item in list_snapshots()]


@router.post("/{meeting_key}/save", response_model=PredictionCompareResponse)
def save_predictions(meeting_key: int) -> PredictionCompareResponse:
    try:
        key = _resolve_key(meeting_key)
        pipeline = _pipeline()
        meeting = pipeline.get_meeting(key)
        classification = _predictor().predict(key)
        race_time = _race_time_predictor().predict(key)
        strategy = _simulator().simulate_grid(key)
        now = _utc_now_iso()
        previous = load_snapshot(key)
        first_saved = (previous or {}).get("first_saved_at") or now
        race_start = pipeline.race_start_at(key) or meeting.date_start
        payload = PredictionSnapshot(
            meeting=meeting,
            race_start_at=race_start,
            first_saved_at=first_saved,
            saved_at=now,
            model_versions=PredictionModelVersions(
                classification=classification.model_version,
                race_time=race_time.model_version,
                strategy=strategy.model_version,
            ),
            classification=SavedClassificationSlice(
                standings=classification.standings,
                note=classification.note,
            ),
            race_time=SavedClassificationSlice(
                standings=race_time.standings,
                note=race_time.note,
            ),
            strategy=SavedStrategySlice(strategies=strategy.strategies),
        )
        save_snapshot(key, payload.model_dump(mode="json"))
        return _compare_from_snapshot(payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{meeting_key}/compare", response_model=PredictionCompareResponse)
def compare_predictions(meeting_key: int) -> PredictionCompareResponse:
    key = _resolve_key(meeting_key)
    raw = load_snapshot(key)
    if raw is None:
        raise HTTPException(status_code=404, detail=f"No saved predictions for meeting {key}")
    try:
        snapshot = PredictionSnapshot.model_validate(raw)
        return _compare_from_snapshot(snapshot)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _compare_from_snapshot(snapshot: PredictionSnapshot) -> PredictionCompareResponse:
    has_actual, positions, durations, actual_strategies = _load_actuals(snapshot.meeting.meeting_key)
    lock = compute_lock_status(
        first_saved_at=snapshot.first_saved_at,
        saved_at=snapshot.saved_at,
        race_start_at=snapshot.race_start_at,
    )
    overwritten = lock == "overwritten_after_start"
    finishes = [
        ActualFinishRow(
            position=pos,
            driver_number=dn,
            duration_s=durations.get(dn),
        )
        for dn, pos in sorted(positions.items(), key=lambda x: x[1])
    ]
    metrics = None
    if has_actual:
        actual_compounds = {a.driver_number: a.compounds for a in actual_strategies}
        metrics = PredictionCompareMetrics(
            classification=classification_metrics(
                [s.model_dump() for s in snapshot.classification.standings],
                positions,
            ),
            race_time=race_time_metrics(
                [s.model_dump() for s in snapshot.race_time.standings],
                durations,
            ),
            strategy=strategy_metrics(
                [s.model_dump() for s in snapshot.strategy.strategies],
                actual_compounds,
            ),
        )
    return PredictionCompareResponse(
        snapshot=snapshot,
        lock_status=lock,
        status="scored" if has_actual else "awaiting_race",
        overwritten=overwritten,
        actual_finishes=finishes,
        actual_strategies=actual_strategies,
        metrics=metrics,
    )
