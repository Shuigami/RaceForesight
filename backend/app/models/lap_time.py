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
from app.models.trained_at import resolve_trained_at, utc_now_iso
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
    VERSION = "xgboost-lap-v4"
    DISPLAY_NAME = "Lap-time XGBoost"

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

    @property
    def trained_at(self) -> str | None:
        return resolve_trained_at(self.meta, self.artifact_dir / self.MODEL_FILE)

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

    @staticmethod
    def season_pace_levels(df: pd.DataFrame) -> tuple[dict[str, float], dict[int, float]]:
        """Dry median pace per circuit, normalised across seasons, plus each season's pace level.

        Regulation changes shift every circuit by a similar factor (2026 ~2% slower than 2025),
        so a single circuit median mixes eras; levels chain year-over-year ratios on shared circuits.
        """
        dry = df[df["compound"].isin(DRY_COMPOUNDS) & (pd.to_numeric(df["rainfall"], errors="coerce").fillna(0) <= 0.05)]
        if dry.empty:
            dry = df
        med = dry.groupby(["circuit_short_name", "year"])["lap_duration"].median().unstack()
        years = sorted(int(y) for y in med.columns)
        levels = {years[0]: 1.0}
        for prev, cur in zip(years, years[1:]):
            ratio = (med[cur] / med[prev]).dropna()
            levels[cur] = levels[prev] * (float(ratio.median()) if not ratio.empty else 1.0)
        pace = med.div(pd.Series(levels)).median(axis=1).dropna().to_dict()
        pace["*"] = float(pd.Series(pace).median())
        return {str(k): float(v) for k, v in pace.items()}, levels

    @staticmethod
    def _season_baseline(df: pd.DataFrame, pace: dict[str, float], levels: dict[int, float]) -> pd.Series:
        circuit_pace = df["circuit_short_name"].astype(str).map(pace).fillna(pace["*"])
        level = df["year"].astype(int).map(levels).fillna(levels[max(levels)])
        return circuit_pace * level

    def train(self, df: pd.DataFrame, *, test_fraction: float = 0.2) -> dict:
        if df.empty:
            raise ValueError("Training frame is empty")

        work = self._filter_training_laps(df)
        if work.empty:
            raise ValueError("No laps left after SC/wet filters")

        self.features.fit(work)
        work = self.features.transform(work)
        work = work.sort_values(["year", "session_key", "lap_number"])

        split_idx = int(len(work) * (1 - test_fraction))
        train_df = work.iloc[:split_idx].copy()
        test_df = work.iloc[split_idx:].copy()
        if train_df.empty or test_df.empty:
            train_df = work.copy()
            test_df = work.tail(max(50, len(work) // 10)).copy()

        # Baselines from the train split only, so test laps never leak into their own baseline.
        pace, levels = self.season_pace_levels(train_df)
        for part in (train_df, test_df):
            part["baseline"] = self._season_baseline(part, pace, levels)
            part["residual"] = part["lap_duration"] - part["baseline"]

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
        params = dict(
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
        )
        self.model = XGBRegressor(n_estimators=600, early_stopping_rounds=40, **params)
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

        # Live model: refit on every lap (latest races included) with the early-stopped tree count.
        pace, levels = self.season_pace_levels(work)
        work["baseline"] = self._season_baseline(work, pace, levels)
        self.model = XGBRegressor(n_estimators=best_iteration + 1, **params)
        self.model.fit(
            work[FEATURE_COLUMNS].to_numpy(dtype=np.float32),
            (work["lap_duration"] - work["baseline"]).to_numpy(dtype=np.float32),
            sample_weight=work["sample_weight"].to_numpy(dtype=np.float32),
            verbose=False,
        )
        latest = levels[max(levels)]
        baselines = {c: v * latest for c, v in pace.items()}
        baselines.update({k: v for k, v in DEFAULT_CIRCUIT_BASELINES.items() if k not in baselines})
        self.circuit_baselines = {str(k): float(v) for k, v in baselines.items()}

        self.meta = {
            "version": self.VERSION,
            "trained_at": utc_now_iso(),
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
            "baseline": "season_normalised_dry_median",
            "season_levels": {str(y): round(v, 5) for y, v in levels.items()},
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
