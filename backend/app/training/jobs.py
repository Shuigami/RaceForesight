"""Single-flight async train jobs with per-model session progress."""

from __future__ import annotations

import threading
import uuid
from copy import deepcopy
from datetime import datetime, timezone

from app.data.pipeline import RaceDataPipeline
from app.training.runners import TRAIN_TARGETS, train_target

DEFAULT_YEARS = [2023, 2024, 2025, 2026]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _empty_model_state() -> dict:
    return {
        "status": "pending",
        "stage": None,
        "current": 0,
        "total": 0,
        "error": None,
    }


def invalidate_model_caches() -> None:
    """Drop cached predictors so the next request loads fresh .joblib files."""
    try:
        from app.api.routes import models as models_routes
        from app.api.routes import races as races_routes

        races_routes._pipeline.cache_clear()
        races_routes._simulator.cache_clear()
        races_routes._predictor.cache_clear()
        races_routes._race_time_predictor.cache_clear()
        models_routes._evaluator.cache_clear()
    except Exception:
        pass


class TrainJobManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._job: dict | None = None

    def status(self) -> dict | None:
        with self._lock:
            return deepcopy(self._job) if self._job else None

    def start(
        self,
        targets: list[str],
        *,
        years: list[int] | None = None,
        max_sessions: int | None = None,
    ) -> dict:
        cleaned = [t for t in targets if t in TRAIN_TARGETS]
        if not cleaned:
            raise ValueError(f"targets must be one of {TRAIN_TARGETS}")
        # Preserve UI section order
        ordered = [t for t in TRAIN_TARGETS if t in cleaned]

        with self._lock:
            if self._job and self._job["status"] in ("queued", "running"):
                raise RuntimeError("A training job is already running")
            job_id = uuid.uuid4().hex[:12]
            self._job = {
                "job_id": job_id,
                "status": "queued",
                "targets": ordered,
                "years": years or list(DEFAULT_YEARS),
                "max_sessions": max_sessions,
                "started_at": _utc_now(),
                "finished_at": None,
                "error": None,
                "models": {t: _empty_model_state() for t in TRAIN_TARGETS},
            }
            for t in ordered:
                self._job["models"][t]["status"] = "queued"
            snapshot = deepcopy(self._job)

        thread = threading.Thread(
            target=self._run,
            args=(job_id, ordered, years or list(DEFAULT_YEARS), max_sessions),
            daemon=True,
            name=f"train-{job_id}",
        )
        thread.start()
        return snapshot

    def _update_model(self, job_id: str, target: str, **fields: object) -> None:
        with self._lock:
            if not self._job or self._job["job_id"] != job_id:
                return
            self._job["models"][target].update(fields)

    def _set_job(self, job_id: str, **fields: object) -> None:
        with self._lock:
            if not self._job or self._job["job_id"] != job_id:
                return
            self._job.update(fields)

    def _run(
        self,
        job_id: str,
        targets: list[str],
        years: list[int],
        max_sessions: int | None,
    ) -> None:
        self._set_job(job_id, status="running")
        pipeline = RaceDataPipeline()
        try:
            for target in targets:
                self._update_model(
                    job_id,
                    target,
                    status="running",
                    stage="starting",
                    current=0,
                    total=0,
                    error=None,
                )

                def on_progress(stage: str, current: int, total: int, _t=target) -> None:
                    self._update_model(
                        job_id,
                        _t,
                        status="running",
                        stage=stage,
                        current=int(current),
                        total=int(total),
                    )

                try:
                    train_target(
                        target,
                        pipeline,
                        years=years,
                        max_sessions=max_sessions,
                        on_progress=on_progress,
                    )
                    self._update_model(
                        job_id,
                        target,
                        status="done",
                        stage="done",
                        current=1,
                        total=1,
                    )
                except Exception as exc:
                    self._update_model(
                        job_id,
                        target,
                        status="error",
                        error=str(exc),
                    )
                    self._set_job(
                        job_id,
                        status="error",
                        error=f"{target}: {exc}",
                        finished_at=_utc_now(),
                    )
                    return

            invalidate_model_caches()
            self._set_job(job_id, status="done", finished_at=_utc_now())
        except Exception as exc:
            self._set_job(job_id, status="error", error=str(exc), finished_at=_utc_now())
        finally:
            pipeline.close()


train_jobs = TrainJobManager()
