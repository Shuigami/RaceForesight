"""Pairwise finishing-order ranker (grid + form + pace)."""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from xgboost import XGBRanker

from app.config import settings
from app.simulation.form import finishing_form, shrunk_pace_offsets, team_form

RANK_FEATURE_COLUMNS = [
    "grid_position",
    "recent_form",
    "circuit_form",
    "pace_offset",
    "team_form",
    "rainfall",
    "n_pace_samples",
    "is_newcomer",
    "grid_missing",
]


class RankingModel:
    MODEL_FILE = "ranking_xgb.joblib"
    META_FILE = "ranking_meta.json"
    VERSION = "ranking-pairwise-v1"

    def __init__(self, artifact_dir: Path | None = None) -> None:
        self.artifact_dir = artifact_dir or settings.model_dir
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self.model: XGBRanker | None = None
        self.meta: dict = {}

    @property
    def is_ready(self) -> bool:
        return (self.artifact_dir / self.MODEL_FILE).exists()

    def build_race_features(
        self,
        *,
        drivers: pd.DataFrame,
        grid: dict[int, int],
        history: pd.DataFrame,
        pace_frame: pd.DataFrame,
        circuit: str,
        rainfall: float = 0.0,
    ) -> pd.DataFrame:
        offsets = shrunk_pace_offsets(pace_frame, drivers, circuit)
        # Approximate sample counts from pace frame
        n_by_driver: dict[int, int] = {}
        if not pace_frame.empty and "driver_number" in pace_frame.columns:
            same = pace_frame[pace_frame["circuit_short_name"].astype(str).str.upper() == circuit.upper()]
            use = same if len(same) > 200 else pace_frame
            n_by_driver = use.groupby("driver_number").size().astype(int).to_dict()
            n_by_driver = {int(k): int(v) for k, v in n_by_driver.items()}

        team_to_drivers: dict[str, list[int]] = {}
        for _, row in drivers.iterrows():
            team = str(row.get("team_name") or "Unknown")
            team_to_drivers.setdefault(team, []).append(int(row["driver_number"]))

        rows = []
        for _, row in drivers.iterrows():
            dnum = int(row["driver_number"])
            team = str(row.get("team_name") or "Unknown")
            recent, n_recent = finishing_form(history, dnum, last_n=5)
            circuit_avg, n_circuit = finishing_form(history, dnum, circuit=circuit, last_n=5)
            n_pace = n_by_driver.get(dnum, 0)
            grid_pos = grid.get(dnum)
            rows.append(
                {
                    "driver_number": dnum,
                    "name_acronym": str(row.get("name_acronym") or f"D{dnum}"),
                    "full_name": str(row.get("full_name") or "Unknown"),
                    "team_name": team,
                    "team_colour": row.get("team_colour"),
                    "grid_position": float(grid_pos) if grid_pos is not None else 11.0,
                    "grid_missing": 0.0 if grid_pos is not None else 1.0,
                    "recent_form": recent,
                    "circuit_form": circuit_avg if n_circuit > 0 else recent,
                    "pace_offset": float(offsets.get(dnum, 0.0)),
                    "team_form": team_form(history, team_to_drivers.get(team, [dnum]), last_n=5),
                    "rainfall": float(rainfall),
                    "n_pace_samples": float(n_pace),
                    "is_newcomer": 1.0 if n_pace < 25 and n_recent < 2 else 0.0,
                    "n_recent_races": n_recent,
                }
            )
        return pd.DataFrame(rows)

    def train(self, race_frames: list[pd.DataFrame]) -> dict:
        """Each frame is one race with RANK_FEATURE_COLUMNS + 'position' label."""
        if not race_frames:
            raise ValueError("No ranking races to train on")

        parts = []
        group_sizes: list[int] = []
        for frame in race_frames:
            work = frame.dropna(subset=["position"]).copy()
            if len(work) < 8:
                continue
            # XGBRanker: lower relevance = worse; invert positions so P1 has highest score
            work = work.sort_values("position")
            work["relevance"] = (work["position"].max() + 1 - work["position"]).astype(float)
            parts.append(work)
            group_sizes.append(len(work))
        if not parts:
            raise ValueError("Insufficient ranking examples")

        data = pd.concat(parts, ignore_index=True)
        x = data[RANK_FEATURE_COLUMNS].to_numpy(dtype=np.float32)
        y = data["relevance"].to_numpy(dtype=np.float32)

        self.model = XGBRanker(
            objective="rank:pairwise",
            n_estimators=250,
            max_depth=5,
            learning_rate=0.06,
            subsample=0.9,
            colsample_bytree=0.9,
            min_child_weight=2,
            n_jobs=4,
            random_state=42,
        )
        self.model.fit(x, y, group=group_sizes)
        self.meta = {
            "version": self.VERSION,
            "n_races": len(group_sizes),
            "n_rows": int(len(data)),
            "feature_columns": RANK_FEATURE_COLUMNS,
        }
        self.save()
        return self.meta

    def predict_order(self, features: pd.DataFrame) -> pd.DataFrame:
        if self.model is None:
            self.load()
        assert self.model is not None
        work = features.copy()
        scores = self.model.predict(work[RANK_FEATURE_COLUMNS].to_numpy(dtype=np.float32))
        work["score"] = scores
        work = work.sort_values("score", ascending=False).reset_index(drop=True)
        work["position"] = np.arange(1, len(work) + 1)
        return work

    def save(self) -> None:
        if self.model is None:
            raise RuntimeError("No ranking model to save")
        joblib.dump(self.model, self.artifact_dir / self.MODEL_FILE)
        (self.artifact_dir / self.META_FILE).write_text(json.dumps(self.meta, indent=2), encoding="utf-8")

    def load(self) -> RankingModel:
        path = self.artifact_dir / self.MODEL_FILE
        if not path.exists():
            raise FileNotFoundError(f"Ranking model not found at {path}")
        self.model = joblib.load(path)
        meta_path = self.artifact_dir / self.META_FILE
        if meta_path.exists():
            self.meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return self
