import pandas as pd

from app.data.pipeline import actual_strategies_from_stints


def test_actual_from_stints_one_stop():
    stints = pd.DataFrame(
        [
            {"driver_number": 1, "stint_number": 1, "compound": "MEDIUM", "lap_start": 1, "lap_end": 20, "tyre_age_at_start": 0},
            {"driver_number": 1, "stint_number": 2, "compound": "HARD", "lap_start": 21, "lap_end": 56, "tyre_age_at_start": 0},
        ]
    )
    out = actual_strategies_from_stints(stints)
    assert len(out) == 1
    a = out[0]
    assert a.driver_number == 1
    assert a.stops == 1
    assert a.compounds == ["MEDIUM", "HARD"]
    assert a.pit_laps == [20]
    assert a.stints[0].lap_start == 1
    assert a.stints[-1].lap_end == 56


def test_actual_empty_stints():
    assert actual_strategies_from_stints(pd.DataFrame()) == []


def test_pits_override_when_count_matches():
    stints = pd.DataFrame(
        [
            {"driver_number": 44, "stint_number": 1, "compound": "SOFT", "lap_start": 1, "lap_end": 15, "tyre_age_at_start": 2},
            {"driver_number": 44, "stint_number": 2, "compound": "HARD", "lap_start": 16, "lap_end": 56, "tyre_age_at_start": 0},
        ]
    )
    pits = pd.DataFrame([{"driver_number": 44, "lap_number": 15}])
    out = actual_strategies_from_stints(stints, pits)
    assert out[0].pit_laps == [15]
