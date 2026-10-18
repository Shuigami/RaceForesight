#!/usr/bin/env python3
"""Train pairwise finishing-order ranker from historical OpenF1 results."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.data.pipeline import RaceDataPipeline
from app.models.ranking import RankingModel


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
        if actual.empty or "position" not in actual.columns:
            continue
        actual = actual.dropna(subset=["position", "driver_number"]).copy()
        actual["position"] = actual["position"].astype(int)
        if len(actual) < 10:
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
        rainfall = float(hist["rainfall"].mean()) if not hist.empty and "rainfall" in hist.columns else 0.0
        # Prefer session rainfall from pace/weather on this race
        weather = pipeline.ingest_session(session_key).get("weather")
        if weather is not None and not weather.empty and "rainfall" in weather.columns:
            rainfall = float(weather["rainfall"].mean())

        ranker = RankingModel()
        feats = ranker.build_race_features(
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
            print(f"  + {circuit} session={session_key} drivers={len(feats)}")
    return labeled


def main() -> None:
    parser = argparse.ArgumentParser(description="Train RaceForesight ranking model")
    parser.add_argument("--years", default="2023,2024,2025,2026")
    parser.add_argument("--max-sessions", type=int, default=60)
    args = parser.parse_args()
    years = [int(y.strip()) for y in args.years.split(",") if y.strip()]

    pipeline = RaceDataPipeline()
    try:
        print(f"Building labeled races years={years} max={args.max_sessions}...")
        labeled = _build_labeled_races(pipeline, years=years, max_sessions=args.max_sessions)
        if len(labeled) < 4:
            raise SystemExit(f"Need >=4 races with results, got {len(labeled)}")
        model = RankingModel()
        meta = model.train(labeled)
        print("Ranking model trained:")
        for k, v in meta.items():
            print(f"  {k}: {v}")
        print(f"Artifacts -> {model.artifact_dir}")
    finally:
        pipeline.close()


if __name__ == "__main__":
    main()
