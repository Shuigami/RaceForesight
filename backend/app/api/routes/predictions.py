from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.api.routes.races import _pipeline, _predictor, _race_time_predictor, _simulator
from app.domain.models import (
    ActualFinishRow,
    PredictionCompareMetrics,
    PredictionCompareResponse,
    PredictionMeetingListItem,
    PredictionModelVersions,
    PredictionSaveListItem,
    PredictionSaveNameBody,
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
from app.predictions.store import (
    create_save,
    delete_save,
    list_meetings,
    list_saves,
    load_save,
    rename_save,
)

router = APIRouter(prefix="/api/predictions", tags=["predictions"])


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _default_save_name(now: str) -> str:
    # "2026-10-25T19:04:00Z" -> "2026-10-25 19:04"
    return now.replace("T", " ")[:16]


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


def _meeting_art(meeting_key: int) -> tuple[str | None, str | None]:
    """Live OpenF1 circuit/flag URLs (fills gaps on older saves)."""
    try:
        m = _pipeline().get_meeting(meeting_key)
        return m.circuit_image, m.country_flag
    except Exception:
        return None, None


def _enrich_meeting(raw: dict) -> PredictionMeetingListItem:
    mk = int(raw["meeting_key"])
    has_actual = bool(_finishing_results(mk)[0])
    live_circuit, live_flag = _meeting_art(mk)
    return PredictionMeetingListItem(
        meeting_key=mk,
        meeting_name=str(raw.get("meeting_name") or mk),
        year=raw.get("year"),
        circuit_short_name=raw.get("circuit_short_name"),
        circuit_image=raw.get("circuit_image") or live_circuit,
        country_flag=raw.get("country_flag") or live_flag,
        first_saved_at=raw.get("first_saved_at"),
        saved_at=raw.get("saved_at"),
        race_start_at=raw.get("race_start_at"),
        save_count=int(raw.get("save_count") or 0),
        has_actual=has_actual,
        status="scored" if has_actual else "awaiting_race",
    )


def _enrich_save(raw: dict) -> PredictionSaveListItem:
    mk = int(raw["meeting_key"])
    has_actual = bool(_finishing_results(mk)[0])
    live_circuit, live_flag = _meeting_art(mk)
    lock = compute_lock_status(
        first_saved_at=raw.get("first_saved_at"),
        saved_at=raw.get("saved_at"),
        race_start_at=raw.get("race_start_at"),
    )
    return PredictionSaveListItem(
        id=str(raw["id"]),
        name=str(raw.get("name") or raw["id"]),
        meeting_key=mk,
        meeting_name=str(raw.get("meeting_name") or mk),
        year=raw.get("year"),
        circuit_short_name=raw.get("circuit_short_name"),
        circuit_image=raw.get("circuit_image") or live_circuit,
        country_flag=raw.get("country_flag") or live_flag,
        first_saved_at=raw.get("first_saved_at"),
        saved_at=raw.get("saved_at"),
        race_start_at=raw.get("race_start_at"),
        has_actual=has_actual,
        lock_status=lock,
        status="scored" if has_actual else "awaiting_race",
    )


@router.get("", response_model=list[PredictionMeetingListItem])
def list_saved_predictions() -> list[PredictionMeetingListItem]:
    return [_enrich_meeting(item) for item in list_meetings()]


@router.get("/{meeting_key}/saves", response_model=list[PredictionSaveListItem])
def list_meeting_saves(meeting_key: int) -> list[PredictionSaveListItem]:
    key = _resolve_key(meeting_key)
    return [_enrich_save(item) for item in list_saves(key)]


@router.post("/{meeting_key}/save", response_model=PredictionCompareResponse)
def save_predictions(
    meeting_key: int,
    body: PredictionSaveNameBody | None = None,
) -> PredictionCompareResponse:
    try:
        key = _resolve_key(meeting_key)
        pipeline = _pipeline()
        meeting = pipeline.get_meeting(key)
        classification = _predictor().predict(key)
        race_time = _race_time_predictor().predict(key)
        strategy = _simulator().simulate_grid(key)
        now = _utc_now_iso()
        name = (body.name.strip() if body and body.name else None) or _default_save_name(now)
        race_start = pipeline.race_start_at(key) or meeting.date_start
        payload = PredictionSnapshot(
            name=name,
            meeting=meeting,
            race_start_at=race_start,
            first_saved_at=now,
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
        stored = create_save(key, payload.model_dump(mode="json"))
        snapshot = PredictionSnapshot.model_validate(stored)
        return _compare_from_snapshot(snapshot)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/{meeting_key}/saves/{save_id}/compare",
    response_model=PredictionCompareResponse,
)
def compare_save(meeting_key: int, save_id: str) -> PredictionCompareResponse:
    key = _resolve_key(meeting_key)
    raw = load_save(key, save_id)
    if raw is None:
        raise HTTPException(
            status_code=404,
            detail=f"No save {save_id} for meeting {key}",
        )
    try:
        snapshot = PredictionSnapshot.model_validate(raw)
        return _compare_from_snapshot(snapshot)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.patch("/{meeting_key}/saves/{save_id}", response_model=PredictionSaveListItem)
def rename_meeting_save(
    meeting_key: int,
    save_id: str,
    body: PredictionSaveNameBody,
) -> PredictionSaveListItem:
    key = _resolve_key(meeting_key)
    if not body.name or not body.name.strip():
        raise HTTPException(status_code=400, detail="name is required")
    raw = rename_save(key, save_id, body.name)
    if raw is None:
        raise HTTPException(
            status_code=404,
            detail=f"No save {save_id} for meeting {key}",
        )
    meeting = raw.get("meeting") or {}
    return _enrich_save(
        {
            "id": raw.get("id") or save_id,
            "name": raw.get("name") or save_id,
            "meeting_key": meeting.get("meeting_key") or key,
            "meeting_name": meeting.get("meeting_name") or key,
            "year": meeting.get("year"),
            "circuit_short_name": meeting.get("circuit_short_name"),
            "circuit_image": meeting.get("circuit_image"),
            "country_flag": meeting.get("country_flag"),
            "first_saved_at": raw.get("first_saved_at"),
            "saved_at": raw.get("saved_at"),
            "race_start_at": raw.get("race_start_at"),
        }
    )


@router.delete("/{meeting_key}/saves/{save_id}")
def delete_meeting_save(meeting_key: int, save_id: str) -> dict[str, bool]:
    key = _resolve_key(meeting_key)
    if not delete_save(key, save_id):
        raise HTTPException(
            status_code=404,
            detail=f"No save {save_id} for meeting {key}",
        )
    return {"ok": True}


def _compare_from_snapshot(snapshot: PredictionSnapshot) -> PredictionCompareResponse:
    has_actual, positions, durations, actual_strategies = _load_actuals(snapshot.meeting.meeting_key)
    live_circuit, live_flag = _meeting_art(snapshot.meeting.meeting_key)
    if live_circuit or live_flag:
        snapshot = snapshot.model_copy(
            update={
                "meeting": snapshot.meeting.model_copy(
                    update={
                        "circuit_image": snapshot.meeting.circuit_image or live_circuit,
                        "country_flag": snapshot.meeting.country_flag or live_flag,
                    }
                )
            }
        )
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
