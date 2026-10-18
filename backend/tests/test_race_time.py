"""Unit checks for race-time duration normalization and feature enrichment."""

from __future__ import annotations

import pandas as pd

from app.models.race_time import RaceTimeModel, normalize_race_duration_s


def test_normalize_race_duration_seconds() -> None:
    assert normalize_race_duration_s(5500.5) == 5500.5


def test_normalize_race_duration_milliseconds() -> None:
    assert normalize_race_duration_s(5_500_500) == 5500.5


def test_normalize_race_duration_rejects_junk() -> None:
    assert normalize_race_duration_s(None) is None
    assert normalize_race_duration_s(0) is None
    assert normalize_race_duration_s(100) is None


def test_enrich_features_adds_proxy() -> None:
    model = RaceTimeModel()
    base = pd.DataFrame(
        {
            "driver_number": [1],
            "pace_offset": [-0.2],
            "grid_position": [1.0],
            "grid_missing": [0.0],
            "recent_form": [3.0],
            "circuit_form": [3.0],
            "team_form": [4.0],
            "rainfall": [0.0],
            "n_pace_samples": [100.0],
            "is_newcomer": [0.0],
        }
    )
    out = model.enrich_features(base, circuit="COTA", race_laps=56, pit_loss=22.0)
    assert out.loc[0, "race_laps"] == 56.0
    assert out.loc[0, "pit_loss"] == 22.0
    expected = (out.loc[0, "circuit_baseline"] - 0.2) * 56.0 + 22.0
    assert abs(out.loc[0, "pace_race_proxy"] - expected) < 1e-6
