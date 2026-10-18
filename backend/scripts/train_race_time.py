#!/usr/bin/env python3
"""Train race-duration regressor from OpenF1 session_result.duration."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.data.pipeline import RaceDataPipeline
from app.domain.circuit_laps import resolve_race_laps
from app.models.race_time import RaceTimeModel, normalize_race_duration_s


def _build_labeled_races(
    pipeline: RaceDataPipeline,
    *,
    years: list[int],
    max_sessions: int,
) -> list:
    sessions = pipeline.list_race_sessions(years)
    if sessions.empty:
        return []
    sessions = sessions.sort_values("date_start").tail(max_sessions)
    history_all = pipeline.race_results_history(years=years, max_sessions=max_sessions + 5)
    pace = pipeline.build_training_frame(years=years, max_sessions=max_sessions, completed_only=True)
    model = RaceTimeModel()

    labeled = []
    for _, sess in sessions.iterrows():
        session_key = int(sess["session_key"])
        meeting_key = int(sess["meeting_key"])
        circuit = str(sess.get("circuit_short_name") or "")
        try:
            actual = pipeline.client.session_result(session_key)
        except Exception as exc:
            print(f"skip {session_key}: {exc}")
            continue
        if actual.empty or "driver_number" not in actual.columns:
            continue

        duration_col = "duration" if "duration" in actual.columns else None
        if duration_col is None:
            continue

        time_map: dict[int, float] = {}
        for _, row in actual.dropna(subset=["driver_number"]).iterrows():
            if bool(row.get("dnf")) or bool(row.get("dns")) or bool(row.get("dsq")):
                continue
            dnum = int(row["driver_number"])
            dur = normalize_race_duration_s(row.get(duration_col))
            if dur is not None:
                time_map[dnum] = dur
        if len(time_map) < 8:
            continue

        drivers = pipeline.ingest_session(session_key)["drivers"]
        if drivers.empty:
            continue
        drivers = drivers.drop_duplicates(subset=["driver_number"])
        if "team_name" in drivers.columns:
            drivers = drivers[drivers["team_name"].notna()]

        hist = history_all[history_all["session_key"].astype(int) != session_key] if not history_all.empty else history_all
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
            print(f"  + {circuit} session={session_key} drivers={len(feats)}")
    return labeled


def main() -> None:
    parser = argparse.ArgumentParser(description="Train RaceForesight race-time model")
    parser.add_argument("--years", default="2023,2024,2025,2026")
    parser.add_argument("--max-sessions", type=int, default=60)
    args = parser.parse_args()
    years = [int(y.strip()) for y in args.years.split(",") if y.strip()]

    pipeline = RaceDataPipeline()
    try:
        print(f"Building labeled race times years={years} max={args.max_sessions}...")
        labeled = _build_labeled_races(pipeline, years=years, max_sessions=args.max_sessions)
        if len(labeled) < 4:
            raise SystemExit(f"Need >=4 races with duration labels, got {len(labeled)}")
        model = RaceTimeModel()
        meta = model.train(labeled)
        print("Race-time model trained:")
        for k, v in meta.items():
            print(f"  {k}: {v}")
        print(f"Artifacts -> {model.artifact_dir}")
    finally:
        pipeline.close()


if __name__ == "__main__":
    main()
