"""Feature engineering for lap-time models."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from app.config import settings

FEATURE_COLUMNS = [
    "tyre_age",
    "lap_number",
    "fuel_proxy",
    "track_temp",
    "rainfall",
    "compound_code",
    "driver_code",
    "team_code",
    "circuit_code",
]

COMPOUND_MAP = {
    "SOFT": 0,
    "MEDIUM": 1,
    "HARD": 2,
    "INTERMEDIATE": 3,
    "WET": 4,
    "UNKNOWN": 5,
}


class FeatureBuilder:
    def __init__(self, artifact_dir: Path | None = None) -> None:
        self.artifact_dir = artifact_dir or settings.model_dir
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self.driver_map: dict[str, int] = {}
        self.team_map: dict[str, int] = {}
        self.circuit_map: dict[str, int] = {}

    def _maps_path(self) -> Path:
        return self.artifact_dir / "feature_maps.json"

    def fit(self, df: pd.DataFrame) -> FeatureBuilder:
        drivers = sorted({str(x) for x in df.get("driver_number", pd.Series(dtype=int)).dropna().tolist()})
        teams = sorted({str(x) for x in df.get("team_name", pd.Series(dtype=str)).fillna("Unknown").tolist()})
        circuits = sorted({str(x) for x in df.get("circuit_short_name", pd.Series(dtype=str)).fillna("UNK").tolist()})
        self.driver_map = {k: i for i, k in enumerate(drivers)}
        self.team_map = {k: i for i, k in enumerate(teams)}
        self.circuit_map = {k: i for i, k in enumerate(circuits)}
        return self

    def save(self) -> None:
        payload = {
            "driver_map": self.driver_map,
            "team_map": self.team_map,
            "circuit_map": self.circuit_map,
        }
        self._maps_path().write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def load(self) -> FeatureBuilder:
        path = self._maps_path()
        if not path.exists():
            return self
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.driver_map = payload.get("driver_map", {})
        self.team_map = payload.get("team_map", {})
        self.circuit_map = payload.get("circuit_map", {})
        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out["compound"] = out.get("compound", "UNKNOWN").astype(str).str.upper()
        out["compound_code"] = out["compound"].map(COMPOUND_MAP).fillna(5).astype(int)
        out["driver_code"] = out["driver_number"].astype(str).map(self.driver_map).fillna(-1).astype(int)
        out["team_code"] = out.get("team_name", "Unknown").fillna("Unknown").astype(str).map(self.team_map).fillna(-1).astype(int)
        out["circuit_code"] = (
            out.get("circuit_short_name", "UNK").fillna("UNK").astype(str).map(self.circuit_map).fillna(-1).astype(int)
        )
        for col in ["tyre_age", "lap_number", "fuel_proxy", "track_temp", "rainfall"]:
            if col not in out.columns:
                out[col] = 0.0
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)
        return out

    def matrix(self, df: pd.DataFrame) -> np.ndarray:
        transformed = self.transform(df)
        return transformed[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
