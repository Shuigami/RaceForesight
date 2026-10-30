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
from app.models.trained_at import resolve_trained_at, utc_now_iso
from app.models.xgb_device import force_xgb_cpu, xgb_device

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
    DURATION_BASELINES_FILE = "race_time_circuit_baselines.json"
    VERSION = "race-time-xgb-v2"
    DISPLAY_NAME = "Race time (XGBoost)"

    def __init__(self, artifact_dir: Path | None = None) -> None:
        self.artifact_dir = artifact_dir or settings.model_dir
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self.model: XGBRegressor | None = None
        self.meta: dict = {}
        self.duration_baselines: dict[str, float] = {"*": 5600.0}
        self._ranker = RankingModel(self.artifact_dir)

    def _duration_baseline_for(self, circuit: str) -> float:
        if circuit in self.duration_baselines:
            return float(self.duration_baselines[circuit])
        return float(self.duration_baselines.get("*", 5600.0))

    @property
    def is_ready(self) -> bool:
        return (self.artifact_dir / self.MODEL_FILE).exists()

    @property
    def trained_at(self) -> str | None:
        return resolve_trained_at(self.meta, self.artifact_dir / self.MODEL_FILE)

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
        work["circuit_short_name"] = circuit
        work["race_laps"] = laps
        work["circuit_baseline"] = baseline
        work["pit_loss"] = float(pit_loss)
        work["pace_race_proxy"] = (baseline + work["pace_offset"].astype(float)) * laps + float(pit_loss)
        work["duration_baseline"] = self._duration_baseline_for(circuit)
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
        """Each frame is one race with RACE_TIME_FEATURE_COLUMNS + race_time_s label.

        Learns within-race gaps; absolute time = circuit duration median + gap.
        Absolute MAE is dominated by SC/red-flag variance (~7–10 min ceiling).
        """
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
        if "session_key" in data.columns:
            data = data.sort_values(["session_key", "driver_number"])
        if "circuit_short_name" not in data.columns:
            data["circuit_short_name"] = "*"

        split_idx = int(len(data) * (1 - test_fraction))
        train_df = data.iloc[:split_idx].copy()
        test_df = data.iloc[split_idx:].copy()
        if train_df.empty or test_df.empty:
            train_df = data.copy()
            test_df = data.tail(max(20, len(data) // 10)).copy()

        baselines = train_df.groupby("circuit_short_name")["race_time_s"].median().to_dict()
        baselines["*"] = float(train_df["race_time_s"].median())
        self.duration_baselines = {str(k): float(v) for k, v in baselines.items()}

        if "session_key" not in train_df.columns:
            train_df["session_key"] = 0
        train_df["race_mean"] = train_df.groupby("session_key")["race_time_s"].transform("mean")
        train_df["gap"] = train_df["race_time_s"] - train_df["race_mean"]
        test_df["duration_baseline"] = (
            test_df["circuit_short_name"].map(self.duration_baselines).fillna(self.duration_baselines["*"])
        )
        if "session_key" not in test_df.columns:
            test_df["session_key"] = 0

        es_idx = max(1, int(len(train_df) * 0.85))
        fit_df, es_df = train_df.iloc[:es_idx], train_df.iloc[es_idx:]
        if es_df.empty:
            fit_df = train_df
            es_df = train_df.tail(max(10, len(train_df) // 10))

        x_fit = fit_df[RACE_TIME_FEATURE_COLUMNS].to_numpy(dtype=np.float32)
        y_fit = fit_df["gap"].to_numpy(dtype=np.float32)
        x_es = es_df[RACE_TIME_FEATURE_COLUMNS].to_numpy(dtype=np.float32)
        y_es = es_df["gap"].to_numpy(dtype=np.float32)
        x_test = test_df[RACE_TIME_FEATURE_COLUMNS].to_numpy(dtype=np.float32)
        y_test = test_df["race_time_s"].to_numpy(dtype=np.float32)

        device = xgb_device()
        # Tuned 2026-10: within-race gaps + circuit duration prior; shallow + L2.
        self.model = XGBRegressor(
            n_estimators=400,
            max_depth=3,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            min_child_weight=5,
            reg_lambda=8.0,
            reg_alpha=0.5,
            device=device,
            n_jobs=4,
            random_state=42,
            early_stopping_rounds=25,
        )
        self.model.fit(x_fit, y_fit, eval_set=[(x_es, y_es)], verbose=False)
        gap_hat = self.model.predict(x_test)
        pred = test_df["duration_baseline"].to_numpy(dtype=np.float32) + gap_hat
        mae = float(mean_absolute_error(y_test, pred))
        rmse = float(np.sqrt(mean_squared_error(y_test, pred)))
        within_vals = []
        tmp = test_df.copy()
        tmp["pred"] = pred
        for _, g in tmp.groupby("session_key"):
            if len(g) < 6:
                continue
            within_vals.append(
                float(
                    np.mean(
                        np.abs(
                            (g["race_time_s"] - g["race_time_s"].mean())
                            - (g["pred"] - g["pred"].mean())
                        )
                    )
                )
            )
        within_mae = float(np.mean(within_vals)) if within_vals else None
        best_iteration = int(getattr(self.model, "best_iteration", None) or self.model.n_estimators)
        self.meta = {
            "version": self.VERSION,
            "trained_at": utc_now_iso(),
            "device": device,
            "n_races": len(parts),
            "n_train": int(len(train_df)),
            "n_test": int(len(test_df)),
            "mae_s": round(mae, 4),
            "rmse_s": round(rmse, 4),
            "within_race_mae_s": round(within_mae, 4) if within_mae is not None else None,
            "best_iteration": best_iteration,
            "feature_columns": RACE_TIME_FEATURE_COLUMNS,
            "target": "within_race_gap_plus_circuit_duration",
        }
        self.save()
        return self.meta

    def predict(self, features: pd.DataFrame) -> pd.DataFrame:
        if self.model is None:
            self.load()
        assert self.model is not None
        work = features.copy()
        if "duration_baseline" not in work.columns:
            circuits = work.get("circuit_short_name", pd.Series(["*"] * len(work))).astype(str)
            work["duration_baseline"] = [self._duration_baseline_for(c) for c in circuits]
        gap = self.model.predict(work[RACE_TIME_FEATURE_COLUMNS].to_numpy(dtype=np.float32))
        work["predicted_race_time_s"] = work["duration_baseline"].to_numpy(dtype=np.float32) + gap
        work = work.sort_values("predicted_race_time_s").reset_index(drop=True)
        work["position"] = np.arange(1, len(work) + 1)
        return work

    def save(self) -> None:
        if self.model is None:
            raise RuntimeError("No race-time model to save")
        joblib.dump(self.model, self.artifact_dir / self.MODEL_FILE)
        (self.artifact_dir / self.META_FILE).write_text(json.dumps(self.meta, indent=2), encoding="utf-8")
        (self.artifact_dir / self.DURATION_BASELINES_FILE).write_text(
            json.dumps(self.duration_baselines, indent=2), encoding="utf-8"
        )

    def load(self) -> RaceTimeModel:
        path = self.artifact_dir / self.MODEL_FILE
        if not path.exists():
            raise FileNotFoundError(f"Race-time model not found at {path}")
        self.model = force_xgb_cpu(joblib.load(path))
        meta_path = self.artifact_dir / self.META_FILE
        if meta_path.exists():
            self.meta = json.loads(meta_path.read_text(encoding="utf-8"))
        baselines_path = self.artifact_dir / self.DURATION_BASELINES_FILE
        if baselines_path.exists():
            self.duration_baselines = {
                str(k): float(v) for k, v in json.loads(baselines_path.read_text(encoding="utf-8")).items()
            }
        return self
