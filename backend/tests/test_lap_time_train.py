"""Smoke test for lap-time XGB train path (early stopping + metrics)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.models.lap_time import LapTimeModel


def test_train_returns_mae_and_best_iteration(tmp_path):
    rng = np.random.default_rng(0)
    n = 400
    df = pd.DataFrame(
        {
            "lap_duration": 90 + rng.normal(0, 1.0, n),
            "session_key": np.repeat(np.arange(10), 40),
            "year": 2025,
            "lap_number": np.tile(np.arange(1, 41), 10),
            "circuit_short_name": "Monza",
            "compound": "MEDIUM",
            "tyre_age": np.tile(np.arange(40), 10),
            "driver_number": 1,
            "team_name": "Test",
            "fuel_proxy": 40,
            "track_temp": 35.0,
            "rainfall": 0.0,
            "stint_length": 40,
            "stint_lap": np.tile(np.arange(1, 41), 10),
            "is_outlap": 0,
            "field_delta": 0.0,
            "neutralization_intensity": 0.0,
        }
    )
    model = LapTimeModel(tmp_path)
    meta = model.train(df, test_fraction=0.2)
    assert meta["mae"] < 3.0
    assert meta["best_iteration"] >= 0
    assert model.is_ready
