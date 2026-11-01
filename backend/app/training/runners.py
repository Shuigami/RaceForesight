"""Shared train runners used by CLI scripts and the async job API."""

from __future__ import annotations

import pandas as pd

from app.data.pipeline import ProgressCallback, RaceDataPipeline
from app.domain.circuit_laps import resolve_race_laps
from app.models.lap_time import LapTimeModel
from app.models.race_time import RaceTimeModel, normalize_race_duration_s
from app.models.ranking import RankingModel

TRAIN_TARGETS = ("lap_time", "classification", "race_time")

ProgressFn = ProgressCallback


def _noop_progress(_stage: str, _current: int, _total: int) -> None:
    return None


def train_lap_time(
    pipeline: RaceDataPipeline,
    *,
    years: list[int],
    max_sessions: int = 80,
    on_progress: ProgressFn | None = None,
) -> dict:
    progress = on_progress or _noop_progress
    frame = pipeline.build_training_frame(
        years=years,
        max_sessions=max_sessions,
        completed_only=True,
        on_progress=progress,
        progress_stage="pace",
    )
    if frame.empty:
        raise ValueError("No training data available from OpenF1")
    progress("fit", 0, 1)
    meta = LapTimeModel().train(frame)
    progress("fit", 1, 1)
    return meta


def _race_contexts(
    pipeline: RaceDataPipeline,
    *,
    years: list[int],
    max_sessions: int,
    progress: ProgressFn,
):
    """Yield (session row, session_result, drivers, past-only history, past-only pace, grid, rainfall).

    Form and pace only use races that started before this one: the old "all but this race"
    filter leaked future results into training features and inflated backtests.
    """
    sessions = pipeline.list_race_sessions(years)
    if sessions.empty:
        raise ValueError("No race sessions found")
    sessions = sessions.sort_values("date_start").tail(max_sessions)
    history_all = pipeline.race_results_history(
        years=years,
        max_sessions=max_sessions + 5,
        on_progress=progress,
        progress_stage="history",
    )
    pace = pipeline.build_training_frame(
        years=years,
        max_sessions=max_sessions,
        completed_only=True,
        on_progress=progress,
        progress_stage="pace",
    )
    all_sessions = pipeline.list_race_sessions(years)
    started = dict(
        zip(all_sessions["session_key"].astype(int), pd.to_datetime(all_sessions["date_start"], utc=True, errors="coerce"))
    )
    hist_start = (
        pd.to_datetime(history_all["date_start"], utc=True, errors="coerce") if not history_all.empty else None
    )
    pace_start = pace["session_key"].astype(int).map(started) if not pace.empty else None

    total = len(sessions)
    for i, (_, sess) in enumerate(sessions.iterrows(), start=1):
        session_key = int(sess["session_key"])
        try:
            actual = pipeline.client.session_result(session_key)
        except Exception:
            actual = pd.DataFrame()
        data = pipeline.ingest_session(session_key) if not actual.empty else {}
        drivers = data.get("drivers", pd.DataFrame())
        if actual.empty or drivers.empty or "driver_number" not in actual.columns:
            progress("label", i, total)
            continue
        drivers = drivers.drop_duplicates(subset=["driver_number"])
        if "team_name" in drivers.columns:
            drivers = drivers[drivers["team_name"].notna()]

        start = started.get(session_key)
        hist = history_all[hist_start < start] if hist_start is not None else history_all
        pace_ex = pace[pace_start < start] if pace_start is not None else pace
        weather = data.get("weather")
        rainfall = (
            float(weather["rainfall"].mean())
            if weather is not None and not weather.empty and "rainfall" in weather.columns
            else 0.0
        )
        grid = pipeline.qualifying_grid(int(sess["meeting_key"]))
        yield sess, actual, drivers, hist, pace_ex, grid, rainfall
        progress("label", i, total)


def build_classification_frames(
    pipeline: RaceDataPipeline,
    *,
    years: list[int],
    max_sessions: int = 60,
    on_progress: ProgressFn | None = None,
) -> list[pd.DataFrame]:
    """One labelled frame per race (RANK_FEATURE_COLUMNS + position), oldest first."""
    labeled = []
    for sess, actual, drivers, hist, pace_ex, grid, rainfall in _race_contexts(
        pipeline, years=years, max_sessions=max_sessions, progress=on_progress or _noop_progress
    ):
        if "position" not in actual.columns:
            continue
        actual = actual.dropna(subset=["position", "driver_number"])
        if len(actual) < 10:
            continue
        circuit = str(sess.get("circuit_short_name") or "")
        feats = RankingModel().build_race_features(
            drivers=drivers,
            grid=grid,
            history=hist,
            pace_frame=pace_ex,
            circuit=circuit,
            rainfall=rainfall,
        )
        pos_map = {int(r["driver_number"]): int(r["position"]) for _, r in actual.iterrows()}
        feats["position"] = feats["driver_number"].map(pos_map)
        feats["session_key"] = int(sess["session_key"])
        feats["circuit_short_name"] = circuit
        feats = feats.dropna(subset=["position"])
        if len(feats) >= 8:
            labeled.append(feats)
    return labeled


def build_race_time_frames(
    pipeline: RaceDataPipeline,
    *,
    years: list[int],
    max_sessions: int = 60,
    on_progress: ProgressFn | None = None,
) -> list[pd.DataFrame]:
    """One labelled frame per race (RACE_TIME_FEATURE_COLUMNS + race_time_s), oldest first."""
    model = RaceTimeModel()
    labeled = []
    for sess, actual, drivers, hist, pace_ex, grid, rainfall in _race_contexts(
        pipeline, years=years, max_sessions=max_sessions, progress=on_progress or _noop_progress
    ):
        if "duration" not in actual.columns:
            continue
        time_map: dict[int, float] = {}
        for _, row in actual.dropna(subset=["driver_number"]).iterrows():
            if bool(row.get("dnf")) or bool(row.get("dns")) or bool(row.get("dsq")):
                continue
            dur = normalize_race_duration_s(row.get("duration"))
            if dur is not None:
                time_map[int(row["driver_number"])] = dur
        if len(time_map) < 8:
            continue
        circuit = str(sess.get("circuit_short_name") or "")
        feats = model.build_race_features(
            drivers=drivers,
            grid=grid,
            history=hist,
            pace_frame=pace_ex,
            circuit=circuit,
            rainfall=rainfall,
            race_laps=resolve_race_laps(circuit),
            pit_loss=pipeline.estimate_pit_loss(circuit_short_name=circuit),
        )
        feats["race_time_s"] = feats["driver_number"].map(time_map)
        feats["session_key"] = int(sess["session_key"])
        feats["circuit_short_name"] = circuit
        feats = feats.dropna(subset=["race_time_s"])
        if len(feats) >= 8:
            labeled.append(feats)
    return labeled


def train_classification(
    pipeline: RaceDataPipeline,
    *,
    years: list[int],
    max_sessions: int = 60,
    on_progress: ProgressFn | None = None,
) -> dict:
    progress = on_progress or _noop_progress
    labeled = build_classification_frames(pipeline, years=years, max_sessions=max_sessions, on_progress=progress)
    if len(labeled) < 4:
        raise ValueError(f"Need >=4 races with results, got {len(labeled)}")
    progress("fit", 0, 1)
    meta = RankingModel().train(labeled)
    progress("fit", 1, 1)
    return meta


def train_race_time(
    pipeline: RaceDataPipeline,
    *,
    years: list[int],
    max_sessions: int = 60,
    on_progress: ProgressFn | None = None,
) -> dict:
    progress = on_progress or _noop_progress
    labeled = build_race_time_frames(pipeline, years=years, max_sessions=max_sessions, on_progress=progress)
    if len(labeled) < 4:
        raise ValueError(f"Need >=4 races with duration labels, got {len(labeled)}")
    progress("fit", 0, 1)
    meta = RaceTimeModel().train(labeled)
    progress("fit", 1, 1)
    return meta


def train_target(
    target: str,
    pipeline: RaceDataPipeline,
    *,
    years: list[int],
    max_sessions: int | None = None,
    on_progress: ProgressFn | None = None,
) -> dict:
    if target == "lap_time":
        return train_lap_time(
            pipeline,
            years=years,
            max_sessions=max_sessions or 80,
            on_progress=on_progress,
        )
    if target == "classification":
        return train_classification(
            pipeline,
            years=years,
            max_sessions=max_sessions or 60,
            on_progress=on_progress,
        )
    if target == "race_time":
        return train_race_time(
            pipeline,
            years=years,
            max_sessions=max_sessions or 60,
            on_progress=on_progress,
        )
    raise ValueError(f"Unknown train target: {target}")
