"""XGBoost lap-time regressor."""

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


class LapTimeModel:
    MODEL_FILE = "lap_time_xgb.joblib"
    META_FILE = "lap_time_meta.json"

    def __init__(self, artifact_dir: Path | None = None) -> None:
        self.artifact_dir = artifact_dir or settings.model_dir
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self.features = FeatureBuilder(self.artifact_dir)
        self.model: XGBRegressor | None = None
        self.meta: dict = {}

    @property
    def is_ready(self) -> bool:
        return (self.artifact_dir / self.MODEL_FILE).exists()

    def train(self, df: pd.DataFrame, *, test_fraction: float = 0.2) -> dict:
        if df.empty:
            raise ValueError("Training frame is empty")

        work = df.dropna(subset=["lap_duration"]).copy()
        # Filter extreme outliers (crashes / red flags)
        q01, q99 = work["lap_duration"].quantile(0.01), work["lap_duration"].quantile(0.99)
        work = work[(work["lap_duration"] >= q01) & (work["lap_duration"] <= q99)]

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
        y_train = train_df["lap_duration"].to_numpy(dtype=np.float32)
        x_test = test_df[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
        y_test = test_df["lap_duration"].to_numpy(dtype=np.float32)

        self.model = XGBRegressor(
            n_estimators=250,
            max_depth=6,
            learning_rate=0.08,
            subsample=0.9,
            colsample_bytree=0.9,
            objective="reg:squarederror",
            n_jobs=4,
            random_state=42,
        )
        self.model.fit(x_train, y_train)
        preds = self.model.predict(x_test)
        mae = float(mean_absolute_error(y_test, preds))
        rmse = float(np.sqrt(mean_squared_error(y_test, preds)))

        self.meta = {
            "version": "xgboost-lap-v1",
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

    def load(self) -> LapTimeModel:
        model_path = self.artifact_dir / self.MODEL_FILE
        if not model_path.exists():
            raise FileNotFoundError(f"Model not found at {model_path}. Run scripts/train_model.py first.")
        self.model = joblib.load(model_path)
        self.features.load()
        meta_path = self.artifact_dir / self.META_FILE
        if meta_path.exists():
            self.meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return self

    def predict_laps(self, df: pd.DataFrame) -> np.ndarray:
        if self.model is None:
            self.load()
        assert self.model is not None
        x = self.features.matrix(df)
        return self.model.predict(x)

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
