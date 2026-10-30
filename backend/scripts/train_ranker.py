#!/usr/bin/env python3
"""Train pairwise finishing-order ranker from historical OpenF1 results."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.data.pipeline import RaceDataPipeline
from app.training.runners import train_classification


def main() -> None:
    parser = argparse.ArgumentParser(description="Train RaceForesight ranking model")
    parser.add_argument("--years", default="2023,2024,2025,2026")
    parser.add_argument("--max-sessions", type=int, default=60)
    args = parser.parse_args()
    years = [int(y.strip()) for y in args.years.split(",") if y.strip()]

    pipeline = RaceDataPipeline()
    try:
        print(f"Building labeled races years={years} max={args.max_sessions}...")
        meta = train_classification(
            pipeline,
            years=years,
            max_sessions=args.max_sessions,
            on_progress=lambda stage, cur, tot: print(f"  [{stage}] {cur}/{tot}"),
        )
        print("Ranking model trained:")
        for k, v in meta.items():
            print(f"  {k}: {v}")
    finally:
        pipeline.close()


if __name__ == "__main__":
    main()
