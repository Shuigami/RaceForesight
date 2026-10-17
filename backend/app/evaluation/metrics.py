"""Evaluate lap-time and classification models; persist scores for the Models UI."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from scipy.stats import kendalltau, spearmanr

from app.config import settings
from app.data.pipeline import RaceDataPipeline
from app.domain.models import ModelScore, ModelsMetricsResponse
from app.features.builder import FEATURE_COLUMNS, FeatureBuilder
from app.models.lap_time import LapTimeModel
from app.simulation.prediction import ClassificationPredictor


class ModelEvaluator:
    METRICS_FILE = "model_metrics.json"

    def __init__(self, artifact_dir: Path | None = None, pipeline: RaceDataPipeline | None = None) -> None:
        self.artifact_dir = artifact_dir or settings.model_dir
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self.pipeline = pipeline or RaceDataPipeline()
        self.owns_pipeline = pipeline is None

    def close(self) -> None:
        if self.owns_pipeline:
            self.pipeline.close()

    def metrics_path(self) -> Path:
        return self.artifact_dir / self.METRICS_FILE

    def load(self) -> ModelsMetricsResponse | None:
        path = self.metrics_path()
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return ModelsMetricsResponse(**payload)

    def save(self, response: ModelsMetricsResponse) -> None:
        self.metrics_path().write_text(response.model_dump_json(indent=2), encoding="utf-8")

    def evaluate(
        self,
        *,
        years: list[int] | None = None,
        max_sessions: int = 12,
        ranking_races: int = 6,
    ) -> ModelsMetricsResponse:
        years = years or [2024, 2025]
        frame = self.pipeline.build_training_frame(years=years, max_sessions=max_sessions)
        if frame.empty:
            raise RuntimeError("No training data available for evaluation")

        xgb_score = self._score_xgboost(frame)
        rf_score = self._score_random_forest(frame)
        ranking_score, n_races, notes = self._score_ranking(years=years, max_races=ranking_races)

        response = ModelsMetricsResponse(
            generated_at=datetime.now(timezone.utc).isoformat(),
            models=[xgb_score, rf_score, ranking_score],
            evaluation_races=n_races,
            notes=notes,
        )
        self.save(response)
        return response

    def _prepare_supervised(self, df: pd.DataFrame) -> tuple[pd.DataFrame, FeatureBuilder, dict[str, float]]:
        work = df.dropna(subset=["lap_duration"]).copy()
        work["session_med"] = work.groupby("session_key")["lap_duration"].transform("median")
        work = work[
            (work["lap_duration"] <= work["session_med"] * 1.07)
            & (work["lap_duration"] >= work["session_med"] * 0.92)
            & (work["compound"].isin(["SOFT", "MEDIUM", "HARD"]))
        ].drop(columns=["session_med"])

        baselines = work.groupby("circuit_short_name")["lap_duration"].median().to_dict()
        baselines["*"] = float(work["lap_duration"].median())
        work["baseline"] = work["circuit_short_name"].map(baselines).fillna(baselines["*"])
        work["residual"] = work["lap_duration"] - work["baseline"]

        features = FeatureBuilder(self.artifact_dir)
        features.fit(work)
        work = features.transform(work).sort_values(["year", "session_key", "lap_number"])
        return work, features, {str(k): float(v) for k, v in baselines.items()}

    def _temporal_split(self, work: pd.DataFrame, test_fraction: float = 0.2):
        split_idx = int(len(work) * (1 - test_fraction))
        train_df = work.iloc[:split_idx]
        test_df = work.iloc[split_idx:]
        if train_df.empty or test_df.empty:
            train_df = work
            test_df = work.tail(max(50, len(work) // 10))
        return train_df, test_df

    def _score_xgboost(self, frame: pd.DataFrame) -> ModelScore:
        # Prefer already-trained primary model metrics; recompute if missing
        lap = LapTimeModel(self.artifact_dir)
        if lap.is_ready:
            lap.load()
            meta = lap.meta
            return ModelScore(
                name="Lap-time XGBoost",
                kind="lap_time",
                version=str(meta.get("version", "xgboost-lap-v1")),
                primary=True,
                metrics={
                    "mae_s": round(float(meta.get("mae", 0)), 4),
                    "rmse_s": round(float(meta.get("rmse", 0)), 4),
                    "n_train": int(meta.get("n_train", 0)),
                    "n_test": int(meta.get("n_test", 0)),
                    "target": str(meta.get("target", "circuit_residual")),
                },
                description="Primary lap-time model used by strategy simulation (circuit baseline + residual).",
            )

        work, _, _ = self._prepare_supervised(frame)
        train_df, test_df = self._temporal_split(work)
        # Fallback: train quickly if no artifact
        model = LapTimeModel(self.artifact_dir)
        meta = model.train(frame)
        return ModelScore(
            name="Lap-time XGBoost",
            kind="lap_time",
            version=str(meta.get("version", "xgboost-lap-v1")),
            primary=True,
            metrics={
                "mae_s": round(float(meta["mae"]), 4),
                "rmse_s": round(float(meta["rmse"]), 4),
                "n_train": int(meta["n_train"]),
                "n_test": int(meta["n_test"]),
                "target": "circuit_residual",
            },
            description="Primary lap-time model used by strategy simulation.",
        )

    def _score_random_forest(self, frame: pd.DataFrame) -> ModelScore:
        work, _, _ = self._prepare_supervised(frame)
        train_df, test_df = self._temporal_split(work)
        x_train = train_df[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
        y_train = train_df["residual"].to_numpy(dtype=np.float32)
        x_test = test_df[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
        y_abs = test_df["lap_duration"].to_numpy(dtype=np.float32)
        baseline = test_df["baseline"].to_numpy(dtype=np.float32)

        rf = RandomForestRegressor(
            n_estimators=200,
            max_depth=12,
            min_samples_leaf=3,
            n_jobs=4,
            random_state=42,
        )
        rf.fit(x_train, y_train)
        preds = baseline + rf.predict(x_test)
        mae = float(mean_absolute_error(y_abs, preds))
        rmse = float(np.sqrt(mean_squared_error(y_abs, preds)))
        # R² on absolute lap times
        ss_res = float(np.sum((y_abs - preds) ** 2))
        ss_tot = float(np.sum((y_abs - np.mean(y_abs)) ** 2)) or 1.0
        r2 = 1.0 - ss_res / ss_tot

        return ModelScore(
            name="Lap-time Random Forest",
            kind="lap_time",
            version="rf-lap-v1",
            primary=False,
            metrics={
                "mae_s": round(mae, 4),
                "rmse_s": round(rmse, 4),
                "r2": round(r2, 4),
                "n_train": int(len(train_df)),
                "n_test": int(len(test_df)),
                "target": "circuit_residual",
            },
            description="Benchmark regressor on the same features/split as XGBoost (not used in live inference).",
        )

    def _score_ranking(self, *, years: list[int], max_races: int) -> tuple[ModelScore, int, list[str]]:
        sessions = self.pipeline.list_race_sessions(years)
        notes: list[str] = []
        if sessions.empty:
            return (
                ModelScore(
                    name="Classification (pace ranking)",
                    kind="classification",
                    version="ranking-strategy-v1",
                    primary=True,
                    metrics={},
                    description="No historical race sessions available for backtest.",
                ),
                0,
                ["No race sessions found for ranking evaluation."],
            )

        # Prefer completed races with results (skip future / empty)
        sessions = sessions.sort_values("date_start")
        evaluated = 0
        spearman_vals: list[float] = []
        kendall_vals: list[float] = []
        top3_hits: list[float] = []
        mae_pos: list[float] = []

        lap_model = LapTimeModel()
        if lap_model.is_ready:
            lap_model.load()
        predictor = ClassificationPredictor(simulator=None)

        # Evaluate newest completed races first
        for _, sess in sessions.iloc[::-1].iterrows():
            if evaluated >= max_races:
                break
            session_key = int(sess["session_key"])
            meeting_key = int(sess["meeting_key"])
            try:
                actual = self.pipeline.client.session_result(session_key)
            except Exception as exc:
                notes.append(f"session_result failed for {session_key}: {exc}")
                continue
            if actual.empty or "position" not in actual.columns:
                continue
            actual = actual.dropna(subset=["position"]).copy()
            actual["position"] = actual["position"].astype(int)
            if len(actual) < 10:
                continue

            try:
                meeting = self.pipeline.get_meeting(meeting_key)
            except Exception:
                continue
            meeting.circuit_short_name = str(sess.get("circuit_short_name") or meeting.circuit_short_name)
            drivers = self.pipeline.ingest_session(session_key)["drivers"]
            if drivers.empty:
                continue
            drivers = drivers.drop_duplicates(subset=["driver_number"])
            if "team_name" in drivers.columns:
                drivers = drivers[drivers["team_name"].notna()]
            drivers = drivers.head(20)

            offsets = {}
            try:
                # Reuse simulator pace helper without full strategy search
                from app.simulation.strategy import StrategySimulator

                sim = StrategySimulator(pipeline=self.pipeline, model=lap_model if lap_model.is_ready else None)
                offsets = sim._pace_offsets(drivers, meeting.circuit_short_name or "UNK")
            except Exception:
                offsets = {int(d): 0.0 for d in drivers["driver_number"].tolist()}

            baseline = 90.0
            if lap_model.is_ready:
                baseline = lap_model._baseline_for(meeting.circuit_short_name or "*")
            pit_loss = self.pipeline.estimate_pit_loss(circuit_short_name=meeting.circuit_short_name or "COTA")

            predicted = predictor.predict_lightweight(
                meeting,
                drivers,
                pace_offsets=offsets,
                pit_loss=pit_loss,
                circuit_baseline=baseline,
            )
            pred_map = {p.driver_number: p.position for p in predicted}
            pairs = []
            for _, row in actual.iterrows():
                dnum = int(row["driver_number"])
                if dnum in pred_map:
                    pairs.append((pred_map[dnum], int(row["position"])))
            if len(pairs) < 8:
                continue

            pred_pos = np.array([p[0] for p in pairs], dtype=float)
            true_pos = np.array([p[1] for p in pairs], dtype=float)
            sp = spearmanr(pred_pos, true_pos).correlation
            kt = kendalltau(pred_pos, true_pos).correlation
            if sp is not None and not np.isnan(sp):
                spearman_vals.append(float(sp))
            if kt is not None and not np.isnan(kt):
                kendall_vals.append(float(kt))

            pred_top3 = {p.driver_number for p in predicted if p.position <= 3}
            true_top3 = set(actual.loc[actual["position"] <= 3, "driver_number"].astype(int).tolist())
            if true_top3:
                top3_hits.append(len(pred_top3 & true_top3) / 3.0)
            mae_pos.append(float(np.mean(np.abs(pred_pos - true_pos))))
            evaluated += 1

        metrics: dict[str, float | int | str | None] = {
            "races_evaluated": evaluated,
            "spearman": round(float(np.mean(spearman_vals)), 4) if spearman_vals else None,
            "kendall_tau": round(float(np.mean(kendall_vals)), 4) if kendall_vals else None,
            "top3_hit_rate": round(float(np.mean(top3_hits)), 4) if top3_hits else None,
            "mae_position": round(float(np.mean(mae_pos)), 4) if mae_pos else None,
        }
        if evaluated == 0:
            notes.append("Could not evaluate ranking on any race (missing session_result).")

        score = ModelScore(
            name="Classification (pace ranking)",
            kind="classification",
            version="ranking-strategy-v1",
            primary=True,
            metrics=metrics,
            description=(
                "Backtest of finishing-order prediction vs OpenF1 session_result. "
                "Uses pace-offset ranking (lightweight proxy of the live strategy-time ranking)."
            ),
        )
        return score, evaluated, notes
