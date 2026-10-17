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
from app.features.builder import FEATURE_COLUMNS, FeatureBuilder

# Sensible COTA dry-race baseline when historical COTA data is sparse
DEFAULT_CIRCUIT_BASELINES = {
    "COTA": 98.5,
    "Austin": 98.5,
}


class LapTimeModel:
    MODEL_FILE = "lap_time_xgb.joblib"
    META_FILE = "lap_time_meta.json"
    BASELINES_FILE = "circuit_baselines.json"

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
        # fallback: global median baseline stored as "*"
        return float(self.circuit_baselines.get("*", 90.0))

    def train(self, df: pd.DataFrame, *, test_fraction: float = 0.2) -> dict:
        if df.empty:
            raise ValueError("Training frame is empty")

        work = df.dropna(subset=["lap_duration"]).copy()
        work["session_med"] = work.groupby("session_key")["lap_duration"].transform("median")
        work = work[
            (work["lap_duration"] <= work["session_med"] * 1.07)
            & (work["lap_duration"] >= work["session_med"] * 0.92)
        ]
        work = work[work["compound"].isin(["SOFT", "MEDIUM", "HARD"])]
        work = work.drop(columns=["session_med"])

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
        x_test = test_df[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
        y_test_abs = test_df["lap_duration"].to_numpy(dtype=np.float32)
        baseline_test = test_df["baseline"].to_numpy(dtype=np.float32)

        self.model = XGBRegressor(
            n_estimators=300,
            max_depth=5,
            learning_rate=0.06,
            subsample=0.85,
            colsample_bytree=0.85,
            min_child_weight=3,
            objective="reg:squarederror",
            n_jobs=4,
            random_state=42,
        )
        self.model.fit(x_train, y_train)
        preds = baseline_test + self.model.predict(x_test)
        mae = float(mean_absolute_error(y_test_abs, preds))
        rmse = float(np.sqrt(mean_squared_error(y_test_abs, preds)))

        self.meta = {
            "version": "xgboost-lap-v1",
            "target": "circuit_residual",
            "n_train": int(len(train_df)),
            "n_test": int(len(test_df)),
            "mae": mae,
            "rmse": rmse,
            "feature_columns": FEATURE_COLUMNS,
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
        self.model = joblib.load(model_path)
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
        rows = []
        for lap in range(lap_start, lap_end + 1):
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
                }
            )
        preds = self.predict_laps(pd.DataFrame(rows))
        return [float(p + pace_offset) for p in preds]
