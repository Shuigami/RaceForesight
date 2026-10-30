"""Shared train runners used by CLI scripts and the async job API."""

from __future__ import annotations

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


def train_classification(
    pipeline: RaceDataPipeline,
    *,
    years: list[int],
    max_sessions: int = 60,
    on_progress: ProgressFn | None = None,
) -> dict:
    progress = on_progress or _noop_progress
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

    labeled = []
    total = len(sessions)
    for i, (_, sess) in enumerate(sessions.iterrows(), start=1):
        session_key = int(sess["session_key"])
        meeting_key = int(sess["meeting_key"])
        circuit = str(sess.get("circuit_short_name") or "")
        try:
            actual = pipeline.client.session_result(session_key)
        except Exception:
            progress("label", i, total)
            continue
        if actual.empty or "position" not in actual.columns:
            progress("label", i, total)
            continue
        actual = actual.dropna(subset=["position", "driver_number"]).copy()
        actual["position"] = actual["position"].astype(int)
        if len(actual) < 10:
            progress("label", i, total)
            continue

        drivers = pipeline.ingest_session(session_key)["drivers"]
        if drivers.empty:
            progress("label", i, total)
            continue
        drivers = drivers.drop_duplicates(subset=["driver_number"])
        if "team_name" in drivers.columns:
            drivers = drivers[drivers["team_name"].notna()]

        hist = (
            history_all[history_all["session_key"].astype(int) != session_key]
            if not history_all.empty
            else history_all
        )
        pace_ex = pace[pace["session_key"].astype(int) != session_key] if not pace.empty else pace
        grid = pipeline.qualifying_grid(meeting_key)
        rainfall = float(hist["rainfall"].mean()) if not hist.empty and "rainfall" in hist.columns else 0.0
        weather = pipeline.ingest_session(session_key).get("weather")
        if weather is not None and not weather.empty and "rainfall" in weather.columns:
            rainfall = float(weather["rainfall"].mean())

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
        feats = feats.dropna(subset=["position"])
        if len(feats) >= 8:
            labeled.append(feats)
        progress("label", i, total)

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
    model = RaceTimeModel()

    labeled = []
    total = len(sessions)
    for i, (_, sess) in enumerate(sessions.iterrows(), start=1):
        session_key = int(sess["session_key"])
        meeting_key = int(sess["meeting_key"])
        circuit = str(sess.get("circuit_short_name") or "")
        try:
            actual = pipeline.client.session_result(session_key)
        except Exception:
            progress("label", i, total)
            continue
        if actual.empty or "driver_number" not in actual.columns or "duration" not in actual.columns:
            progress("label", i, total)
            continue

        time_map: dict[int, float] = {}
        for _, row in actual.dropna(subset=["driver_number"]).iterrows():
            if bool(row.get("dnf")) or bool(row.get("dns")) or bool(row.get("dsq")):
                continue
            dnum = int(row["driver_number"])
            dur = normalize_race_duration_s(row.get("duration"))
            if dur is not None:
                time_map[dnum] = dur
        if len(time_map) < 8:
            progress("label", i, total)
            continue

        drivers = pipeline.ingest_session(session_key)["drivers"]
        if drivers.empty:
            progress("label", i, total)
            continue
        drivers = drivers.drop_duplicates(subset=["driver_number"])
        if "team_name" in drivers.columns:
            drivers = drivers[drivers["team_name"].notna()]

        hist = (
            history_all[history_all["session_key"].astype(int) != session_key]
            if not history_all.empty
            else history_all
        )
        pace_ex = pace[pace["session_key"].astype(int) != session_key] if not pace.empty else pace
        grid = pipeline.qualifying_grid(meeting_key)
        weather = pipeline.ingest_session(session_key).get("weather")
        rainfall = (
            float(weather["rainfall"].mean())
            if weather is not None and not weather.empty and "rainfall" in weather.columns
            else 0.0
        )
        race_laps = resolve_race_laps(circuit)
        pit_loss = pipeline.estimate_pit_loss(circuit_short_name=circuit)

        feats = model.build_race_features(
            drivers=drivers,
            grid=grid,
            history=hist,
            pace_frame=pace_ex,
            circuit=circuit,
            rainfall=rainfall,
            race_laps=race_laps,
            pit_loss=pit_loss,
        )
        feats["race_time_s"] = feats["driver_number"].map(time_map)
        feats["session_key"] = session_key
        feats["circuit_short_name"] = circuit
        feats = feats.dropna(subset=["race_time_s"])
        if len(feats) >= 8:
            labeled.append(feats)
        progress("label", i, total)

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
