#!/usr/bin/env python3
"""Ingest OpenF1 race data and train the XGBoost lap-time model."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.data.pipeline import RaceDataPipeline
from app.training.runners import train_lap_time


def main() -> None:
    parser = argparse.ArgumentParser(description="Train RaceForesight lap-time model")
    parser.add_argument("--years", default="2023,2024,2025,2026", help="Comma-separated seasons")
    parser.add_argument(
        "--max-sessions",
        type=int,
        default=80,
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

        if args.include_future:
            # Rare path kept for CLI; shared runner uses completed_only=True
            from app.models.lap_time import LapTimeModel

            frame = pipeline.build_training_frame(
                years=years,
                max_sessions=args.max_sessions,
                completed_only=False,
            )
            if frame.empty:
                raise SystemExit("No training data available from OpenF1")
            metrics = LapTimeModel().train(frame)
        else:
            metrics = train_lap_time(
                pipeline,
                years=years,
                max_sessions=args.max_sessions,
                on_progress=lambda stage, cur, tot: print(f"  [{stage}] {cur}/{tot}"),
            )
        print("Training complete:")
        for k, v in metrics.items():
            print(f"  {k}: {v}")
    finally:
        pipeline.close()


if __name__ == "__main__":
    main()
