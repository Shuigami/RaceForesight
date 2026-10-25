"""XGBoost lap-time regressor (circuit-baseline + residual)."""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
from xgboost import XGBRegressor

from app.config import settings
from app.features.builder import DRY_COMPOUNDS, FEATURE_COLUMNS, WET_COMPOUNDS, FeatureBuilder
from app.models.xgb_device import force_xgb_cpu, xgb_device

# Sensible COTA dry-race baseline when historical COTA data is sparse
DEFAULT_CIRCUIT_BASELINES = {
    "COTA": 98.5,
    "Austin": 98.5,
}


class LapTimeModel:
    MODEL_FILE = "lap_time_xgb.joblib"
    META_FILE = "lap_time_meta.json"
    BASELINES_FILE = "circuit_baselines.json"
    VERSION = "xgboost-lap-v3"

    def __init__(self, artifact_dir: Path | None = None) -> None:
        self.artifact_dir = artifact_dir or settings.model_dir
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self.features = FeatureBuilder(self.artifact_dir)
        self.model: XGBRegressor | None = None
        self.meta: dict = {}
        self.circuit_baselines: dict[str, float] = dict(DEFAULT_CIRCUIT_BASELINES)

    @property
    def is_ready(self) -> bool:
        return (self.artifact_dir / self.MODEL_FILE).exists()

    def _baseline_for(self, circuit: str) -> float:
        if circuit in self.circuit_baselines:
            return float(self.circuit_baselines[circuit])
        return float(self.circuit_baselines.get("*", 90.0))

    @staticmethod
    def _filter_training_laps(df: pd.DataFrame) -> pd.DataFrame:
        """Keep competitive laps; include wet compounds; downweight SC-heavy sessions."""
        work = df.dropna(subset=["lap_duration"]).copy()
        work["compound"] = work["compound"].astype(str).str.upper()
        work["session_med"] = work.groupby("session_key")["lap_duration"].transform("median")
        ratio = work["lap_duration"] / work["session_med"].replace(0, np.nan)

        dry_ok = work["compound"].isin(DRY_COMPOUNDS) & ratio.between(0.93, 1.06)
        wet_ok = work["compound"].isin(WET_COMPOUNDS) & ratio.between(0.85, 1.25)
        # Keep dry when raining if compound still dry (mixed conditions)
        rain = pd.to_numeric(work.get("rainfall", 0), errors="coerce").fillna(0.0)
        mixed_dry = work["compound"].isin(DRY_COMPOUNDS) & (rain > 0.05) & ratio.between(0.90, 1.12)

        work = work[dry_ok | wet_ok | mixed_dry].copy()
        if "is_outlap" in work.columns:
            work = work[work["is_outlap"].fillna(0).astype(int) == 0]

        # Sample weight: reduce influence of neutralized sessions
        intensity = pd.to_numeric(work.get("neutralization_intensity", 0), errors="coerce").fillna(0.0)
        work["sample_weight"] = (1.0 - 0.7 * intensity.clip(0, 1)).clip(0.25, 1.0)
        return work.drop(columns=["session_med"], errors="ignore")

    def train(self, df: pd.DataFrame, *, test_fraction: float = 0.2) -> dict:
        if df.empty:
            raise ValueError("Training frame is empty")

        work = self._filter_training_laps(df)
        if work.empty:
            raise ValueError("No laps left after SC/wet filters")

        baselines = work.groupby("circuit_short_name")["lap_duration"].median().to_dict()
        baselines["*"] = float(work["lap_duration"].median())
        baselines.update({k: v for k, v in DEFAULT_CIRCUIT_BASELINES.items() if k not in baselines})
        self.circuit_baselines = {str(k): float(v) for k, v in baselines.items()}

        work["baseline"] = work["circuit_short_name"].map(self.circuit_baselines).fillna(self.circuit_baselines["*"])
        work["residual"] = work["lap_duration"] - work["baseline"]

        self.features.fit(work)
        work = self.features.transform(work)
        work = work.sort_values(["year", "session_key", "lap_number"])

        split_idx = int(len(work) * (1 - test_fraction))
        train_df = work.iloc[:split_idx]
        test_df = work.iloc[split_idx:]
        if train_df.empty or test_df.empty:
            train_df = work
            test_df = work.tail(max(50, len(work) // 10))

        x_train = train_df[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
        y_train = train_df["residual"].to_numpy(dtype=np.float32)
        w_train = train_df["sample_weight"].to_numpy(dtype=np.float32)
        x_test = test_df[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
        y_test_abs = test_df["lap_duration"].to_numpy(dtype=np.float32)
        baseline_test = test_df["baseline"].to_numpy(dtype=np.float32)

        # Inner temporal holdout for early stopping (last 10% of train).
        es_idx = max(1, int(len(train_df) * 0.9))
        fit_df, es_df = train_df.iloc[:es_idx], train_df.iloc[es_idx:]
        if es_df.empty:
            fit_df, es_df = train_df, test_df

        x_fit = fit_df[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
        y_fit = fit_df["residual"].to_numpy(dtype=np.float32)
        w_fit = fit_df["sample_weight"].to_numpy(dtype=np.float32)
        x_es = es_df[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
        y_es = es_df["residual"].to_numpy(dtype=np.float32)

        device = xgb_device()
        # Tuned 2026-10: shallower trees + L1 beat depth-6 / 350 trees on temporal holdout.
        self.model = XGBRegressor(
            n_estimators=400,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.9,
            colsample_bytree=0.9,
            min_child_weight=5,
            reg_lambda=1.0,
            reg_alpha=0.5,
            gamma=0.0,
            objective="reg:squarederror",
            device=device,
            n_jobs=4,
            random_state=42,
            early_stopping_rounds=40,
        )
        self.model.fit(
            x_fit,
            y_fit,
            sample_weight=w_fit,
            eval_set=[(x_es, y_es)],
            verbose=False,
        )
        preds = baseline_test + self.model.predict(x_test)
        mae = float(mean_absolute_error(y_test_abs, preds))
        rmse = float(np.sqrt(mean_squared_error(y_test_abs, preds)))
        best_iteration = int(getattr(self.model, "best_iteration", None) or self.model.n_estimators)

        self.meta = {
            "version": self.VERSION,
            "target": "circuit_residual",
            "device": device,
            "n_train": int(len(train_df)),
            "n_test": int(len(test_df)),
            "mae": mae,
            "rmse": rmse,
            "best_iteration": best_iteration,
            "feature_columns": FEATURE_COLUMNS,
            "wet_compounds": True,
            "sc_downweight": True,
        }
        self.save()
        return self.meta

    def save(self) -> None:
        if self.model is None:
            raise RuntimeError("No model to save")
        joblib.dump(self.model, self.artifact_dir / self.MODEL_FILE)
        self.features.save()
        (self.artifact_dir / self.META_FILE).write_text(json.dumps(self.meta, indent=2), encoding="utf-8")
        (self.artifact_dir / self.BASELINES_FILE).write_text(
            json.dumps(self.circuit_baselines, indent=2), encoding="utf-8"
        )

    def load(self) -> LapTimeModel:
        model_path = self.artifact_dir / self.MODEL_FILE
        if not model_path.exists():
            raise FileNotFoundError(f"Model not found at {model_path}. Run scripts/train_model.py first.")
        self.model = force_xgb_cpu(joblib.load(model_path))
        self.features.load()
        meta_path = self.artifact_dir / self.META_FILE
        if meta_path.exists():
            self.meta = json.loads(meta_path.read_text(encoding="utf-8"))
        baselines_path = self.artifact_dir / self.BASELINES_FILE
        if baselines_path.exists():
            self.circuit_baselines = json.loads(baselines_path.read_text(encoding="utf-8"))
        return self

    def predict_laps(self, df: pd.DataFrame) -> np.ndarray:
        if self.model is None:
            self.load()
        assert self.model is not None
        transformed = self.features.transform(df)
        residuals = self.model.predict(transformed[FEATURE_COLUMNS].to_numpy(dtype=np.float32))
        circuits = transformed.get("circuit_short_name", pd.Series(["*"] * len(transformed))).astype(str)
        baselines = np.array([self._baseline_for(c) for c in circuits], dtype=np.float32)
        return baselines + residuals

    def predict_stint_laps(
        self,
        *,
        driver_number: int,
        team_name: str,
        circuit_short_name: str,
        compound: str,
        lap_start: int,
        lap_end: int,
        tyre_age_at_start: int,
        total_laps: int,
        track_temp: float = 35.0,
        rainfall: float = 0.0,
        pace_offset: float = 0.0,
    ) -> list[float]:
        stint_length = lap_end - lap_start + 1
        rows = []
        for i, lap in enumerate(range(lap_start, lap_end + 1)):
            rows.append(
                {
                    "driver_number": driver_number,
                    "team_name": team_name,
                    "circuit_short_name": circuit_short_name,
                    "compound": compound,
                    "tyre_age": tyre_age_at_start + (lap - lap_start),
                    "lap_number": lap,
                    "fuel_proxy": max(1, total_laps - lap + 1),
                    "track_temp": track_temp,
                    "rainfall": rainfall,
                    "stint_length": stint_length,
                    "stint_lap": i + 1,
                    "is_outlap": 1 if i == 0 and lap_start > 1 else 0,
                    "field_delta": 0.0,
                }
            )
        preds = self.predict_laps(pd.DataFrame(rows))
        return [float(p + pace_offset) for p in preds]
