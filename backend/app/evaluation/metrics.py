"""Evaluate lap-time and classification models; persist scores for the Models UI."""

from __future__ import annotations

import json
import tempfile
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
from app.domain.circuit_laps import resolve_race_laps
from app.models.lap_time import LapTimeModel
from app.models.race_time import RaceTimeModel, normalize_race_duration_s
from app.models.ranking import RankingModel


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

    @staticmethod
    def merge_scores(
        existing: list[ModelScore],
        fresh: list[ModelScore],
    ) -> list[ModelScore]:
        """Upsert by (name, version); keep older versions for the Models UI picker."""
        by_key: dict[tuple[str, str], ModelScore] = {(m.name, m.version): m for m in existing}
        for m in fresh:
            by_key[(m.name, m.version)] = m
        merged = list(by_key.values())
        # If fresh brings a new primary for a kind, demote every other entry of that kind.
        for kind in {m.kind for m in fresh}:
            keep = {(m.name, m.version) for m in fresh if m.kind == kind and m.primary}
            if not keep:
                continue
            for m in merged:
                if m.kind == kind:
                    m.primary = (m.name, m.version) in keep
        return sorted(merged, key=lambda m: (m.kind, m.name, m.version))

    def evaluate(
        self,
        *,
        years: list[int] | None = None,
        max_sessions: int = 60,
        ranking_races: int = 8,
    ) -> ModelsMetricsResponse:
        years = years or [2023, 2024, 2025, 2026]
        frame = self.pipeline.build_training_frame(
            years=years,
            max_sessions=max_sessions,
            completed_only=True,
        )
        if frame.empty:
            raise RuntimeError("No training data available for evaluation")

        xgb_score = self._score_xgboost(frame)
        rf_score = self._score_random_forest(frame)
        ranking_score, n_races, notes = self._score_ranking_loo(years=years, max_races=ranking_races)
        race_time_score, rt_notes = self._score_race_time_loo(years=years, max_races=ranking_races)
        notes.extend(rt_notes)

        previous = self.load()
        merged = self.merge_scores(
            previous.models if previous else [],
            [xgb_score, rf_score, ranking_score, race_time_score],
        )
        response = ModelsMetricsResponse(
            generated_at=datetime.now(timezone.utc).isoformat(),
            models=merged,
            evaluation_races=n_races,
            notes=notes,
        )
        self.save(response)
        return response

    def _prepare_supervised(self, df: pd.DataFrame) -> tuple[pd.DataFrame, FeatureBuilder, dict[str, float]]:
        model = LapTimeModel(self.artifact_dir)
        work = model._filter_training_laps(df)
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
        lap = LapTimeModel(self.artifact_dir)
        if lap.is_ready:
            lap.load()
            meta = lap.meta
            return ModelScore(
                name="Lap-time XGBoost",
                kind="lap_time",
                version=str(meta.get("version", LapTimeModel.VERSION)),
                primary=True,
                metrics={
                    "mae_s": round(float(meta.get("mae", 0)), 4),
                    "rmse_s": round(float(meta.get("rmse", 0)), 4),
                    "n_train": int(meta.get("n_train", 0)),
                    "n_test": int(meta.get("n_test", 0)),
                    "target": str(meta.get("target", "circuit_residual")),
                },
                description=(
                    "Primary lap-time model (circuit baseline + residual). "
                    "Includes compound×age / circuit×compound, stint features, wet compounds, SC downweight."
                ),
            )

        model = LapTimeModel(self.artifact_dir)
        meta = model.train(frame)
        return ModelScore(
            name="Lap-time XGBoost",
            kind="lap_time",
            version=str(meta.get("version", LapTimeModel.VERSION)),
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
        w = train_df["sample_weight"].to_numpy(dtype=np.float32) if "sample_weight" in train_df.columns else None

        rf = RandomForestRegressor(
            n_estimators=200,
            max_depth=12,
            min_samples_leaf=3,
            n_jobs=4,
            random_state=42,
        )
        rf.fit(x_train, y_train, sample_weight=w)
        preds = baseline + rf.predict(x_test)
        mae = float(mean_absolute_error(y_abs, preds))
        rmse = float(np.sqrt(mean_squared_error(y_abs, preds)))
        ss_res = float(np.sum((y_abs - preds) ** 2))
        ss_tot = float(np.sum((y_abs - np.mean(y_abs)) ** 2)) or 1.0
        r2 = 1.0 - ss_res / ss_tot

        return ModelScore(
            name="Lap-time Random Forest",
            kind="lap_time",
            version="rf-lap-v2",
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

    def _build_labeled_races_inline(self, *, years: list[int], max_sessions: int) -> list[pd.DataFrame]:
        sessions = self.pipeline.list_race_sessions(years)
        if sessions.empty:
            return []
        sessions = sessions.sort_values("date_start").tail(max_sessions)
        history_all = self.pipeline.race_results_history(years=years, max_sessions=max_sessions + 5)
        pace = self.pipeline.build_training_frame(years=years, max_sessions=max_sessions, completed_only=True)
        labeled: list[pd.DataFrame] = []
        for _, sess in sessions.iterrows():
            session_key = int(sess["session_key"])
            meeting_key = int(sess["meeting_key"])
            circuit = str(sess.get("circuit_short_name") or "")
            try:
                actual = self.pipeline.client.session_result(session_key)
            except Exception:
                continue
            if actual.empty or "position" not in actual.columns:
                continue
            actual = actual.dropna(subset=["position", "driver_number"]).copy()
            actual["position"] = actual["position"].astype(int)
            if len(actual) < 10:
                continue
            drivers = self.pipeline.ingest_session(session_key)["drivers"]
            if drivers.empty:
                continue
            drivers = drivers.drop_duplicates(subset=["driver_number"])
            if "team_name" in drivers.columns:
                drivers = drivers[drivers["team_name"].notna()]
            hist = history_all[history_all["session_key"].astype(int) != session_key] if not history_all.empty else history_all
            pace_ex = pace[pace["session_key"].astype(int) != session_key] if not pace.empty else pace
            grid = self.pipeline.qualifying_grid(meeting_key)
            weather = self.pipeline.ingest_session(session_key).get("weather", pd.DataFrame())
            rainfall = float(weather["rainfall"].mean()) if not weather.empty and "rainfall" in weather.columns else 0.0
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
            feats["session_key"] = session_key
            feats["circuit_short_name"] = circuit
            feats = feats.dropna(subset=["position"])
            if len(feats) >= 8:
                labeled.append(feats)
        return labeled

    def _score_ranking_loo(self, *, years: list[int], max_races: int) -> tuple[ModelScore, int, list[str]]:
        notes: list[str] = []
        labeled = self._build_labeled_races_inline(years=years, max_sessions=max(40, max_races + 20))
        if len(labeled) < 3:
            return (
                ModelScore(
                    name="Classification (pairwise ranker)",
                    kind="classification",
                    version=RankingModel.VERSION,
                    primary=True,
                    metrics={},
                    description="Insufficient historical races for leave-one-out ranking eval.",
                ),
                0,
                ["Need >=3 races with quali+results for LOO ranking evaluation."],
            )

        holdouts = labeled[-max_races:]
        spearman_vals: list[float] = []
        kendall_vals: list[float] = []
        top3_hits: list[float] = []
        mae_pos: list[float] = []
        evaluated = 0

        for holdout in holdouts:
            sk = int(holdout["session_key"].iloc[0])
            train_set = [f for f in labeled if int(f["session_key"].iloc[0]) != sk]
            if len(train_set) < 3:
                notes.append(f"skip LOO session {sk}: not enough train races")
                continue
            with tempfile.TemporaryDirectory(prefix="rf-rank-loo-") as tmp:
                model = RankingModel(Path(tmp))
                try:
                    model.train(train_set)
                except Exception as exc:
                    notes.append(f"ranker train failed for holdout {sk}: {exc}")
                    continue
                ordered = model.predict_order(holdout)
                pairs = []
                for _, row in ordered.iterrows():
                    true_pos = holdout.loc[holdout["driver_number"] == row["driver_number"], "position"]
                    if true_pos.empty:
                        continue
                    pairs.append((int(row["position"]), int(true_pos.iloc[0]), int(row["driver_number"])))
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
                pred_top3 = {p[2] for p in pairs if p[0] <= 3}
                true_top3 = {p[2] for p in pairs if p[1] <= 3}
                if true_top3:
                    top3_hits.append(len(pred_top3 & true_top3) / 3.0)
                mae_pos.append(float(np.mean(np.abs(pred_pos - true_pos))))
                evaluated += 1
                circuit = str(holdout["circuit_short_name"].iloc[0])
                notes.append(
                    f"LOO {circuit} session={sk}: spearman={sp:.3f} mae_pos={mae_pos[-1]:.2f}"
                    if sp is not None and not np.isnan(sp)
                    else f"LOO {circuit} session={sk}"
                )

        metrics: dict[str, float | int | str | None] = {
            "races_evaluated": evaluated,
            "eval_protocol": "leave_one_race_out",
            "spearman": round(float(np.mean(spearman_vals)), 4) if spearman_vals else None,
            "kendall_tau": round(float(np.mean(kendall_vals)), 4) if kendall_vals else None,
            "top3_hit_rate": round(float(np.mean(top3_hits)), 4) if top3_hits else None,
            "mae_position": round(float(np.mean(mae_pos)), 4) if mae_pos else None,
        }
        if evaluated == 0:
            notes.append("Could not evaluate ranking on any holdout race.")

        score = ModelScore(
            name="Classification (pairwise ranker)",
            kind="classification",
            version=RankingModel.VERSION,
            primary=True,
            metrics=metrics,
            description=(
                "Leave-one-race-out backtest of pairwise XGBRanker vs OpenF1 session_result. "
                "Features: qualifying grid, recent/circuit form, shrunk pace, team form, rain."
            ),
        )
        return score, evaluated, notes

    def _build_labeled_race_times_inline(self, *, years: list[int], max_sessions: int) -> list[pd.DataFrame]:
        sessions = self.pipeline.list_race_sessions(years)
        if sessions.empty:
            return []
        sessions = sessions.sort_values("date_start").tail(max_sessions)
        history_all = self.pipeline.race_results_history(years=years, max_sessions=max_sessions + 5)
        pace = self.pipeline.build_training_frame(years=years, max_sessions=max_sessions, completed_only=True)
        rt = RaceTimeModel(self.artifact_dir)
        labeled: list[pd.DataFrame] = []
        for _, sess in sessions.iterrows():
            session_key = int(sess["session_key"])
            meeting_key = int(sess["meeting_key"])
            circuit = str(sess.get("circuit_short_name") or "")
            try:
                actual = self.pipeline.client.session_result(session_key)
            except Exception:
                continue
            if actual.empty or "driver_number" not in actual.columns or "duration" not in actual.columns:
                continue
            time_map: dict[int, float] = {}
            for _, row in actual.dropna(subset=["driver_number"]).iterrows():
                if bool(row.get("dnf")) or bool(row.get("dns")) or bool(row.get("dsq")):
                    continue
                dur = normalize_race_duration_s(row.get("duration"))
                if dur is not None:
                    time_map[int(row["driver_number"])] = dur
            if len(time_map) < 8:
                continue
            drivers = self.pipeline.ingest_session(session_key)["drivers"]
            if drivers.empty:
                continue
            drivers = drivers.drop_duplicates(subset=["driver_number"])
            if "team_name" in drivers.columns:
                drivers = drivers[drivers["team_name"].notna()]
            hist = history_all[history_all["session_key"].astype(int) != session_key] if not history_all.empty else history_all
            pace_ex = pace[pace["session_key"].astype(int) != session_key] if not pace.empty else pace
            grid = self.pipeline.qualifying_grid(meeting_key)
            weather = self.pipeline.ingest_session(session_key).get("weather", pd.DataFrame())
            rainfall = float(weather["rainfall"].mean()) if not weather.empty and "rainfall" in weather.columns else 0.0
            feats = rt.build_race_features(
                drivers=drivers,
                grid=grid,
                history=hist,
                pace_frame=pace_ex,
                circuit=circuit,
                rainfall=rainfall,
                race_laps=resolve_race_laps(circuit),
                pit_loss=self.pipeline.estimate_pit_loss(circuit_short_name=circuit),
            )
            feats["race_time_s"] = feats["driver_number"].map(time_map)
            feats["session_key"] = session_key
            feats["circuit_short_name"] = circuit
            feats = feats.dropna(subset=["race_time_s"])
            if len(feats) >= 8:
                labeled.append(feats)
        return labeled

    def _score_race_time_loo(self, *, years: list[int], max_races: int) -> tuple[ModelScore, list[str]]:
        notes: list[str] = []
        labeled = self._build_labeled_race_times_inline(years=years, max_sessions=max(40, max_races + 20))
        if len(labeled) < 3:
            return (
                ModelScore(
                    name="Race time (XGBoost)",
                    kind="race_time",
                    version=RaceTimeModel.VERSION,
                    primary=True,
                    metrics={},
                    description="Insufficient historical races with duration labels for LOO eval.",
                ),
                ["Need >=3 races with session_result.duration for LOO race-time evaluation."],
            )

        holdouts = labeled[-max_races:]
        mae_vals: list[float] = []
        rmse_vals: list[float] = []
        evaluated = 0

        for holdout in holdouts:
            sk = int(holdout["session_key"].iloc[0])
            train_set = [f for f in labeled if int(f["session_key"].iloc[0]) != sk]
            if len(train_set) < 3:
                notes.append(f"skip race-time LOO session {sk}: not enough train races")
                continue
            with tempfile.TemporaryDirectory(prefix="rf-rt-loo-") as tmp:
                model = RaceTimeModel(Path(tmp))
                try:
                    model.train(train_set)
                except Exception as exc:
                    notes.append(f"race-time train failed for holdout {sk}: {exc}")
                    continue
                pred = model.predict(holdout)
                pairs = []
                for _, row in pred.iterrows():
                    true = holdout.loc[holdout["driver_number"] == row["driver_number"], "race_time_s"]
                    if true.empty:
                        continue
                    pairs.append((float(row["predicted_race_time_s"]), float(true.iloc[0])))
                if len(pairs) < 6:
                    continue
                y_hat = np.array([p[0] for p in pairs], dtype=float)
                y_true = np.array([p[1] for p in pairs], dtype=float)
                mae = float(mean_absolute_error(y_true, y_hat))
                rmse = float(np.sqrt(mean_squared_error(y_true, y_hat)))
                mae_vals.append(mae)
                rmse_vals.append(rmse)
                evaluated += 1
                circuit = str(holdout["circuit_short_name"].iloc[0])
                notes.append(f"LOO race-time {circuit} session={sk}: mae={mae:.1f}s rmse={rmse:.1f}s")

        metrics: dict[str, float | int | str | None] = {
            "races_evaluated": evaluated,
            "eval_protocol": "leave_one_race_out",
            "mae_s": round(float(np.mean(mae_vals)), 4) if mae_vals else None,
            "rmse_s": round(float(np.mean(rmse_vals)), 4) if rmse_vals else None,
        }
        if RaceTimeModel(self.artifact_dir).is_ready:
            meta = RaceTimeModel(self.artifact_dir).load().meta
            metrics["n_train"] = int(meta.get("n_train", 0))
            metrics["n_test"] = int(meta.get("n_test", 0))
            metrics["target"] = str(meta.get("target", "race_duration_s"))

        if evaluated == 0:
            notes.append("Could not evaluate race-time on any holdout race.")

        score = ModelScore(
            name="Race time (XGBoost)",
            kind="race_time",
            version=RaceTimeModel.VERSION,
            primary=True,
            metrics=metrics,
            description=(
                "Leave-one-race-out MAE/RMSE vs OpenF1 session_result.duration for classified finishers. "
                "Features: grid, form, pace, race distance, pit loss, pace×distance proxy."
            ),
        )
        return score, notes
