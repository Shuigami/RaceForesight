#!/usr/bin/env python3
"""Ingest OpenF1 race data and train the XGBoost lap-time model."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.data.pipeline import RaceDataPipeline
from app.models.lap_time import LapTimeModel


def main() -> None:
    parser = argparse.ArgumentParser(description="Train RaceForesight lap-time model")
    parser.add_argument("--years", default="2025,2026", help="Comma-separated seasons")
    parser.add_argument(
        "--max-sessions",
        type=int,
        default=50,
        help="Cap completed race sessions ingested (tail of calendar)",
    )
    parser.add_argument("--force", action="store_true", help="Re-download session caches")
    parser.add_argument(
        "--include-future",
        action="store_true",
        help="Also try sessions that have not started yet (usually empty)",
    )
    args = parser.parse_args()

    years = [int(y.strip()) for y in args.years.split(",") if y.strip()]
    pipeline = RaceDataPipeline()
    try:
        print(f"Ingesting race sessions for years={years} (max={args.max_sessions})...")
        if args.force:
            sessions = pipeline.list_race_sessions(years)
            for _, sess in sessions.tail(args.max_sessions).iterrows():
                pipeline.ingest_session(int(sess["session_key"]), force=True)

        frame = pipeline.build_training_frame(
            years=years,
            max_sessions=args.max_sessions,
            completed_only=not args.include_future,
        )
        if not frame.empty and "year" in frame.columns:
            print("Rows by year:")
            print(frame["year"].value_counts().sort_index().to_string())
        print(f"Training rows: {len(frame)}")
        if frame.empty:
            raise SystemExit("No training data available from OpenF1")

        model = LapTimeModel()
        metrics = model.train(frame)
        print("Training complete:")
        for k, v in metrics.items():
            print(f"  {k}: {v}")
        print(f"Artifacts saved to {model.artifact_dir}")
    finally:
        pipeline.close()


if __name__ == "__main__":
    main()
