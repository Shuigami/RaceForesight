"""Driver-race duration regressor (grid + form + pace → total race time)."""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
from xgboost import XGBRegressor

from app.config import settings
from app.domain.circuit_laps import resolve_race_laps
from app.models.lap_time import LapTimeModel
from app.models.ranking import RANK_FEATURE_COLUMNS, RankingModel
from app.models.xgb_device import xgb_device

RACE_TIME_FEATURE_COLUMNS = [
    *RANK_FEATURE_COLUMNS,
    "race_laps",
    "circuit_baseline",
    "pit_loss",
    "pace_race_proxy",
]


def normalize_race_duration_s(raw: object) -> float | None:
    """OpenF1 race duration may be seconds or milliseconds."""
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(val) or val <= 0:
        return None
    # Typical GP wall-clock is ~4500–9000s; ms values are ~1e6+.
    if val > 20_000:
        val /= 1000.0
    if val < 1800 or val > 15_000:
        return None
    return float(val)


class RaceTimeModel:
    MODEL_FILE = "race_time_xgb.joblib"
    META_FILE = "race_time_meta.json"
    VERSION = "race-time-xgb-v1"

    def __init__(self, artifact_dir: Path | None = None) -> None:
        self.artifact_dir = artifact_dir or settings.model_dir
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self.model: XGBRegressor | None = None
        self.meta: dict = {}
        self._ranker = RankingModel(self.artifact_dir)

    @property
    def is_ready(self) -> bool:
        return (self.artifact_dir / self.MODEL_FILE).exists()

    def _circuit_baseline(self, circuit: str) -> float:
        lap = LapTimeModel(self.artifact_dir)
        baselines_path = self.artifact_dir / LapTimeModel.BASELINES_FILE
        if baselines_path.exists():
            try:
                lap.circuit_baselines = {
                    str(k): float(v) for k, v in json.loads(baselines_path.read_text(encoding="utf-8")).items()
                }
            except Exception:
                pass
        return lap._baseline_for(circuit)

    def enrich_features(
        self,
        features: pd.DataFrame,
        *,
        circuit: str,
        race_laps: int | None = None,
        pit_loss: float = 22.0,
    ) -> pd.DataFrame:
        work = features.copy()
        laps = float(race_laps if race_laps is not None else resolve_race_laps(circuit))
        baseline = self._circuit_baseline(circuit)
        work["race_laps"] = laps
        work["circuit_baseline"] = baseline
        work["pit_loss"] = float(pit_loss)
        work["pace_race_proxy"] = (baseline + work["pace_offset"].astype(float)) * laps + float(pit_loss)
        return work

    def build_race_features(
        self,
        *,
        drivers: pd.DataFrame,
        grid: dict[int, int],
        history: pd.DataFrame,
        pace_frame: pd.DataFrame,
        circuit: str,
        rainfall: float = 0.0,
        race_laps: int | None = None,
        pit_loss: float = 22.0,
    ) -> pd.DataFrame:
        base = self._ranker.build_race_features(
            drivers=drivers,
            grid=grid,
            history=history,
            pace_frame=pace_frame,
            circuit=circuit,
            rainfall=rainfall,
        )
        return self.enrich_features(base, circuit=circuit, race_laps=race_laps, pit_loss=pit_loss)

    def train(self, race_frames: list[pd.DataFrame], *, test_fraction: float = 0.2) -> dict:
        """Each frame is one race with RACE_TIME_FEATURE_COLUMNS + race_time_s label."""
        if not race_frames:
            raise ValueError("No race-time frames to train on")

        parts = []
        for frame in race_frames:
            work = frame.dropna(subset=["race_time_s"]).copy()
            if len(work) < 6:
                continue
            parts.append(work)
        if len(parts) < 3:
            raise ValueError("Need >=3 races with duration labels")

        data = pd.concat(parts, ignore_index=True)
        # Temporal-ish split: later races last if session_key present
        if "session_key" in data.columns:
            data = data.sort_values(["session_key", "driver_number"])
        split_idx = int(len(data) * (1 - test_fraction))
        train_df = data.iloc[:split_idx]
        test_df = data.iloc[split_idx:]
        if train_df.empty or test_df.empty:
            train_df = data
            test_df = data.tail(max(20, len(data) // 10))

        x_train = train_df[RACE_TIME_FEATURE_COLUMNS].to_numpy(dtype=np.float32)
        y_train = train_df["race_time_s"].to_numpy(dtype=np.float32)
        x_test = test_df[RACE_TIME_FEATURE_COLUMNS].to_numpy(dtype=np.float32)
        y_test = test_df["race_time_s"].to_numpy(dtype=np.float32)

        device = xgb_device()
        self.model = XGBRegressor(
            n_estimators=280,
            max_depth=5,
            learning_rate=0.05,
            subsample=0.9,
            colsample_bytree=0.9,
            min_child_weight=2,
            device=device,
            n_jobs=4,
            random_state=42,
        )
        self.model.fit(x_train, y_train)
        pred = self.model.predict(x_test)
        mae = float(mean_absolute_error(y_test, pred))
        rmse = float(np.sqrt(mean_squared_error(y_test, pred)))
        self.meta = {
            "version": self.VERSION,
            "device": device,
            "n_races": len(parts),
            "n_train": int(len(train_df)),
            "n_test": int(len(test_df)),
            "mae_s": round(mae, 4),
            "rmse_s": round(rmse, 4),
            "feature_columns": RACE_TIME_FEATURE_COLUMNS,
            "target": "race_duration_s",
        }
        self.save()
        return self.meta

    def predict(self, features: pd.DataFrame) -> pd.DataFrame:
        if self.model is None:
            self.load()
        assert self.model is not None
        work = features.copy()
        work["predicted_race_time_s"] = self.model.predict(
            work[RACE_TIME_FEATURE_COLUMNS].to_numpy(dtype=np.float32)
        )
        work = work.sort_values("predicted_race_time_s").reset_index(drop=True)
        work["position"] = np.arange(1, len(work) + 1)
        return work

    def save(self) -> None:
        if self.model is None:
            raise RuntimeError("No race-time model to save")
        joblib.dump(self.model, self.artifact_dir / self.MODEL_FILE)
        (self.artifact_dir / self.META_FILE).write_text(json.dumps(self.meta, indent=2), encoding="utf-8")

    def load(self) -> RaceTimeModel:
        path = self.artifact_dir / self.MODEL_FILE
        if not path.exists():
            raise FileNotFoundError(f"Race-time model not found at {path}")
        self.model = joblib.load(path)
        meta_path = self.artifact_dir / self.META_FILE
        if meta_path.exists():
            self.meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return self
