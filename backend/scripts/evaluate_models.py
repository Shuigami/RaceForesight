#!/usr/bin/env python3
"""Evaluate lap-time and classification models; write metrics artifact for the UI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.evaluation.metrics import ModelEvaluator


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate RaceForesight models")
    parser.add_argument("--years", default="2023,2024,2025,2026")
    parser.add_argument("--max-sessions", type=int, default=60)
    parser.add_argument("--ranking-races", type=int, default=8)
    args = parser.parse_args()
    years = [int(y.strip()) for y in args.years.split(",") if y.strip()]

    evaluator = ModelEvaluator()
    try:
        result = evaluator.evaluate(
            years=years,
            max_sessions=args.max_sessions,
            ranking_races=args.ranking_races,
        )
        print(f"Saved metrics -> {evaluator.metrics_path()}")
        print(f"Generated at: {result.generated_at}")
        print(f"Evaluation races: {result.evaluation_races}")
        for model in result.models:
            print(f"\n[{model.kind}] {model.name} ({model.version})" + (" *" if model.primary else ""))
            for k, v in model.metrics.items():
                print(f"  {k}: {v}")
        if result.notes:
            print("\nNotes:")
            for note in result.notes:
                print(f"  - {note}")
    finally:
        evaluator.close()


if __name__ == "__main__":
    main()
