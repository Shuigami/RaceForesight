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
    VERSION = "race-time-xgb-v3"
    # Median race duration / green-flag field proxy (SC laps, fuel, starts); refit on train.
    DEFAULT_DURATION_RATIO = 1.03
    DISPLAY_NAME = "Race time (XGBoost)"

    def __init__(self, artifact_dir: Path | None = None) -> None:
        self.artifact_dir = artifact_dir or settings.model_dir
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self.model: XGBRegressor | None = None
        self.meta: dict = {}
        self.duration_ratio = self.DEFAULT_DURATION_RATIO
        self._ranker = RankingModel(self.artifact_dir)

    @staticmethod
    def _field_proxy(df: pd.DataFrame) -> pd.Series:
        """Green-flag field race time: circuit lap baseline × laps + one stop."""
        return df["circuit_baseline"].astype(float) * df["race_laps"].astype(float) + df["pit_loss"].astype(float)

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

    def _duration_ratio(self, df: pd.DataFrame) -> float:
        by_race = df.assign(proxy=self._field_proxy(df)).groupby("session_key")
        return float((by_race["race_time_s"].median() / by_race["proxy"].first()).median())

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

        Frames must be oldest first. Learns within-race gaps; absolute time = pace-proxy prior + gap.
        Absolute MAE is dominated by SC/red-flag variance (~7–10 min ceiling).
        """
        if not race_frames:
            raise ValueError("No race-time frames to train on")

        parts = []
        for frame in race_frames:
            work = frame.dropna(subset=["race_time_s"]).copy()
            if len(work) < 6:
                continue
            work["race_idx"] = len(parts)
            parts.append(work)
        if len(parts) < 3:
            raise ValueError("Need >=3 races with duration labels")

        data = pd.concat(parts, ignore_index=True)
        # Split whole races: a row split put half of Monaco 2026 in train and flattered the old prior.
        data["session_key"] = data["race_idx"]
        data["race_mean"] = data.groupby("session_key")["race_time_s"].transform("mean")
        data["gap"] = data["race_time_s"] - data["race_mean"]
        n_test_races = max(1, int(round(len(parts) * test_fraction)))
        train_df = data[data["race_idx"] < len(parts) - n_test_races].copy()
        test_df = data[data["race_idx"] >= len(parts) - n_test_races].copy()

        # Prior = pace proxy × median ratio. Per-circuit duration medians had 1–2 samples and
        # inherited red flags (Monaco 2026 ≈ 2h24), walk-forward MAE 453s → 330s with the ratio.
        self.duration_ratio = self._duration_ratio(train_df)
        test_df["duration_baseline"] = self._field_proxy(test_df) * self.duration_ratio

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
        params = dict(
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
        )
        self.model = XGBRegressor(n_estimators=400, early_stopping_rounds=25, **params)
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

        # Live model: every race (current season included), early-stopped tree count.
        self.duration_ratio = self._duration_ratio(data)
        self.model = XGBRegressor(n_estimators=best_iteration + 1, **params)
        self.model.fit(
            data[RACE_TIME_FEATURE_COLUMNS].to_numpy(dtype=np.float32),
            data["gap"].to_numpy(dtype=np.float32),
            verbose=False,
        )
        self.meta = {
            "version": self.VERSION,
            "trained_at": utc_now_iso(),
            "device": device,
            "n_races": len(parts),
            "n_train": int(len(train_df)),
            "n_test": int(len(test_df)),
            "n_test_races": n_test_races,
            "mae_s": round(mae, 4),
            "rmse_s": round(rmse, 4),
            "within_race_mae_s": round(within_mae, 4) if within_mae is not None else None,
            "duration_ratio": round(self.duration_ratio, 5),
            "best_iteration": best_iteration,
            "feature_columns": RACE_TIME_FEATURE_COLUMNS,
            "target": "within_race_gap_plus_pace_proxy_duration",
        }
        self.save()
        return self.meta

    def predict(self, features: pd.DataFrame) -> pd.DataFrame:
        if self.model is None:
            self.load()
        assert self.model is not None
        work = features.copy()
        work["duration_baseline"] = self._field_proxy(work) * self.duration_ratio
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

    def load(self) -> RaceTimeModel:
        path = self.artifact_dir / self.MODEL_FILE
        if not path.exists():
            raise FileNotFoundError(f"Race-time model not found at {path}")
        self.model = force_xgb_cpu(joblib.load(path))
        meta_path = self.artifact_dir / self.META_FILE
        if meta_path.exists():
            self.meta = json.loads(meta_path.read_text(encoding="utf-8"))
        self.duration_ratio = float(self.meta.get("duration_ratio", self.DEFAULT_DURATION_RATIO))
        return self
