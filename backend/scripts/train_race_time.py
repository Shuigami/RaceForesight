#!/usr/bin/env python3
"""Train race-duration regressor from OpenF1 session_result.duration."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.data.pipeline import RaceDataPipeline
from app.training.runners import train_race_time


def main() -> None:
    parser = argparse.ArgumentParser(description="Train RaceForesight race-time model")
    parser.add_argument("--years", default="2023,2024,2025,2026")
    parser.add_argument("--max-sessions", type=int, default=60)
    args = parser.parse_args()
    years = [int(y.strip()) for y in args.years.split(",") if y.strip()]

    pipeline = RaceDataPipeline()
    try:
        print(f"Building labeled race times years={years} max={args.max_sessions}...")
        meta = train_race_time(
            pipeline,
            years=years,
            max_sessions=args.max_sessions,
            on_progress=lambda stage, cur, tot: print(f"  [{stage}] {cur}/{tot}"),
        )
        print("Race-time model trained:")
        for k, v in meta.items():
            print(f"  {k}: {v}")
    finally:
        pipeline.close()


if __name__ == "__main__":
    main()
