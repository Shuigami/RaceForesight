#!/usr/bin/env python3
"""Leave-one-race-out backtest: train without a GP, predict finishing order, compare to OpenF1 results."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import kendalltau, spearmanr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.data.pipeline import RaceDataPipeline
from app.models.lap_time import LapTimeModel
from app.models.ranking import RankingModel
from app.simulation.form import shrunk_pace_offsets
from app.simulation.prediction import ClassificationPredictor


def main() -> None:
    parser = argparse.ArgumentParser(description="Holdout-race classification backtest")
    parser.add_argument("--meeting-key", type=int, default=1296, help="Holdout meeting (default: Singapore 2026)")
    parser.add_argument("--years", default="2023,2024,2025,2026")
    parser.add_argument("--max-sessions", type=int, default=80)
    args = parser.parse_args()
    years = [int(y.strip()) for y in args.years.split(",") if y.strip()]

    pipeline = RaceDataPipeline()
    try:
        meeting = pipeline.get_meeting(args.meeting_key)
        session_key = pipeline.race_session_key(meeting.meeting_key)
        if not session_key:
            raise SystemExit(f"No Race session for meeting {args.meeting_key}")

        actual = pipeline.client.session_result(session_key)
        if actual.empty or "position" not in actual.columns:
            raise SystemExit(f"No session_result for session {session_key}")
        actual = actual.dropna(subset=["position"]).copy()
        actual["position"] = actual["position"].astype(int)

        print(
            f"Holdout: {meeting.meeting_name} ({meeting.circuit_short_name}) "
            f"meeting={meeting.meeting_key} session={session_key}"
        )

        frame = pipeline.build_training_frame(
            years=years,
            max_sessions=args.max_sessions,
            completed_only=True,
        )
        if frame.empty:
            raise SystemExit("No training data")

        holdout_mask = frame["session_key"].astype(int) == int(session_key)
        train_frame = frame.loc[~holdout_mask].copy()
        holdout_laps = frame.loc[holdout_mask].copy()
        print(
            f"Train rows: {len(train_frame)} | held-out laps: {len(holdout_laps)} "
            f"(excluded session {session_key})"
        )
        if train_frame.empty:
            raise SystemExit("Train frame empty after holdout")

        history = pipeline.race_results_history(
            years=years,
            exclude_session_key=session_key,
            max_sessions=args.max_sessions,
        )
        grid = pipeline.qualifying_grid(meeting.meeting_key)
        print(f"Qualifying grid positions available: {len(grid)}")

        drivers = pipeline.drivers_for_meeting(meeting.meeting_key)
        if drivers.empty:
            raise SystemExit("No drivers for meeting")
        drivers = drivers.drop_duplicates(subset=["driver_number"])
        if "team_name" in drivers.columns:
            drivers = drivers[drivers["team_name"].notna()]

        circuit = meeting.circuit_short_name or "UNK"
        weather = pipeline.ingest_session(session_key).get("weather", pd.DataFrame())
        rainfall = float(weather["rainfall"].mean()) if not weather.empty and "rainfall" in weather.columns else 0.0

        with tempfile.TemporaryDirectory(prefix="rf-holdout-") as tmp:
            tmp_path = Path(tmp)
            lap_model = LapTimeModel(tmp_path)
            meta = lap_model.train(train_frame, test_fraction=0.0)
            print(f"Retrained holdout lap model: n_train={meta['n_train']} mae={meta['mae']:.3f}s")

            # Build labeled races for ranker excluding holdout
            evaluator_years = years
            sessions = pipeline.list_race_sessions(evaluator_years).sort_values("date_start").tail(args.max_sessions)
            labeled = []
            for _, sess in sessions.iterrows():
                sk = int(sess["session_key"])
                if sk == int(session_key):
                    continue
                try:
                    res = pipeline.client.session_result(sk)
                except Exception:
                    continue
                if res.empty or "position" not in res.columns:
                    continue
                res = res.dropna(subset=["position", "driver_number"]).copy()
                if len(res) < 10:
                    continue
                ddf = pipeline.ingest_session(sk)["drivers"]
                if ddf.empty:
                    continue
                ddf = ddf.drop_duplicates(subset=["driver_number"])
                if "team_name" in ddf.columns:
                    ddf = ddf[ddf["team_name"].notna()]
                hist = history[history["session_key"].astype(int) != sk] if not history.empty else history
                pace_ex = train_frame[train_frame["session_key"].astype(int) != sk]
                g = pipeline.qualifying_grid(int(sess["meeting_key"]))
                w = pipeline.ingest_session(sk).get("weather", pd.DataFrame())
                rain = float(w["rainfall"].mean()) if not w.empty and "rainfall" in w.columns else 0.0
                feats = RankingModel().build_race_features(
                    drivers=ddf,
                    grid=g,
                    history=hist,
                    pace_frame=pace_ex,
                    circuit=str(sess.get("circuit_short_name") or ""),
                    rainfall=rain,
                )
                pos_map = {int(r["driver_number"]): int(r["position"]) for _, r in res.iterrows()}
                feats["position"] = feats["driver_number"].map(pos_map)
                feats = feats.dropna(subset=["position"])
                if len(feats) >= 8:
                    labeled.append(feats)

            ranker = RankingModel(tmp_path)
            if len(labeled) >= 3:
                rmeta = ranker.train(labeled)
                print(f"Retrained holdout ranker: n_races={rmeta['n_races']}")
                holdout_feats = ranker.build_race_features(
                    drivers=drivers,
                    grid=grid,
                    history=history,
                    pace_frame=train_frame,
                    circuit=circuit,
                    rainfall=rainfall,
                )
                ordered = ranker.predict_order(holdout_feats)
                predicted_rows = [
                    {
                        "pred": int(r["position"]),
                        "driver": str(r["name_acronym"]),
                        "driver_number": int(r["driver_number"]),
                        "team": str(r["team_name"]),
                        "est_time_s": None,
                    }
                    for _, r in ordered.iterrows()
                ]
            else:
                print("Not enough races for ranker; falling back to pace+grid heuristic")
                offsets = shrunk_pace_offsets(train_frame, drivers, circuit)
                pit_loss = pipeline.estimate_pit_loss(circuit_short_name=circuit)
                baseline = lap_model._baseline_for(circuit)
                predictor = ClassificationPredictor(simulator=None)
                try:
                    preds = predictor.predict_lightweight(
                        meeting,
                        drivers,
                        pace_offsets=offsets,
                        pit_loss=pit_loss,
                        circuit_baseline=baseline,
                        grid=grid,
                    )
                finally:
                    predictor.close()
                predicted_rows = [
                    {
                        "pred": p.position,
                        "driver": p.name_acronym,
                        "driver_number": p.driver_number,
                        "team": p.team_name,
                        "est_time_s": p.estimated_race_time_s,
                    }
                    for p in preds
                ]

        actual_map = {
            int(r["driver_number"]): int(r["position"])
            for _, r in actual.iterrows()
            if pd.notna(r.get("driver_number"))
        }
        rows = []
        for p in predicted_rows:
            true_pos = actual_map.get(p["driver_number"])
            if true_pos is None:
                continue
            rows.append(
                {
                    "pred": p["pred"],
                    "actual": true_pos,
                    "delta": p["pred"] - true_pos,
                    "driver": p["driver"],
                    "team": p["team"],
                    "est_time_s": p["est_time_s"],
                }
            )
        if len(rows) < 8:
            raise SystemExit(f"Too few overlapping drivers ({len(rows)})")

        table = pd.DataFrame(rows).sort_values("pred")
        print("\nPredicted vs actual finishing order:")
        cols = ["pred", "actual", "delta", "driver", "team"]
        if table["est_time_s"].notna().any():
            cols.append("est_time_s")
        print(table[cols].to_string(index=False))

        pred_pos = table["pred"].to_numpy(dtype=float)
        true_pos = table["actual"].to_numpy(dtype=float)
        sp = float(spearmanr(pred_pos, true_pos).correlation)
        kt = float(kendalltau(pred_pos, true_pos).correlation)
        mae = float(np.mean(np.abs(pred_pos - true_pos)))
        top3_pred = set(table.loc[table["pred"] <= 3, "driver"])
        top3_true = set(table.loc[table["actual"] <= 3, "driver"])
        top3_hit = len(top3_pred & top3_true) / 3.0

        print("\nMetrics (holdout ranking):")
        print(f"  spearman:     {sp:.4f}")
        print(f"  kendall_tau:  {kt:.4f}")
        print(f"  mae_position: {mae:.3f}")
        print(f"  top3_hit:     {top3_hit:.3f}  (pred {sorted(top3_pred)} vs true {sorted(top3_true)})")
    finally:
        pipeline.close()


if __name__ == "__main__":
    main()
