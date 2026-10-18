"""Lap-time feature engineering and form shrinkage."""

from __future__ import annotations

import pandas as pd

from app.features.builder import FEATURE_COLUMNS, FeatureBuilder
from app.simulation.form import shrunk_pace_offsets


def test_feature_columns_include_interactions():
    assert "compound_x_tyre_age" in FEATURE_COLUMNS
    assert "circuit_x_compound" in FEATURE_COLUMNS
    assert "stint_length" in FEATURE_COLUMNS
    assert "wet_compound" in FEATURE_COLUMNS


def test_transform_builds_interaction_features(tmp_path):
    fb = FeatureBuilder(tmp_path)
    df = pd.DataFrame(
        [
            {
                "driver_number": 1,
                "team_name": "McLaren",
                "circuit_short_name": "Monza",
                "compound": "SOFT",
                "tyre_age": 5,
                "lap_number": 10,
                "fuel_proxy": 40,
                "track_temp": 40,
                "rainfall": 0,
                "stint_length": 20,
                "stint_lap": 5,
                "is_outlap": 0,
                "field_delta": -0.2,
            }
        ]
    )
    fb.fit(df)
    out = fb.transform(df)
    assert out.loc[0, "compound_x_tyre_age"] == out.loc[0, "compound_code"] * 5
    assert out.loc[0, "wet_compound"] == 0.0
    assert set(FEATURE_COLUMNS).issubset(out.columns)


def test_newcomer_pace_offset_shrinks():
    drivers = pd.DataFrame({"driver_number": [1, 2]})
    # Driver 1 has many laps, driver 2 only a few slower laps
    rows = [{"driver_number": 1, "circuit_short_name": "Monza", "lap_duration": 80.0} for _ in range(50)]
    rows += [{"driver_number": 2, "circuit_short_name": "Monza", "lap_duration": 82.0} for _ in range(5)]
    frame = pd.DataFrame(rows)
    offsets = shrunk_pace_offsets(frame, drivers, "Monza", min_laps_full=40, prior_strength=25.0)
    assert offsets[1] < 0.05  # near field
    assert offsets[2] > 0  # slower, but shrunk
    # Without shrink raw would be ~2s; with prior+min_laps should be much smaller
    assert offsets[2] < 1.5
