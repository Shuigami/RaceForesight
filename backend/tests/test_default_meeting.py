from datetime import datetime, timezone

import pandas as pd

from app.data.pipeline import pick_default_meeting_key


def _meetings() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "meeting_key": 1297,
                "meeting_name": "United States Grand Prix",
                "circuit_short_name": "Austin",
                "country_name": "United States",
                "date_start": "2026-10-23T17:30:00+00:00",
            },
            {
                "meeting_key": 1298,
                "meeting_name": "Mexico City Grand Prix",
                "circuit_short_name": "Mexico City",
                "country_name": "Mexico",
                "date_start": "2026-10-30T18:30:00+00:00",
            },
            {
                "meeting_key": 1300,
                "meeting_name": "Las Vegas Grand Prix",
                "circuit_short_name": "Las Vegas",
                "country_name": "United States",
                "date_start": "2026-11-20T00:30:00+00:00",
            },
        ]
    )


def test_race_sunday_still_picks_austin_not_vegas() -> None:
    # Sunday of US GP weekend (meeting started Friday)
    now = datetime(2026, 10, 25, 17, 0, tzinfo=timezone.utc)
    assert pick_default_meeting_key(_meetings(), now=now) == 1297


def test_after_weekend_falls_back_to_latest_austin() -> None:
    now = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)
    assert pick_default_meeting_key(_meetings(), now=now) == 1297


def test_before_weekend_picks_upcoming_austin() -> None:
    now = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
    assert pick_default_meeting_key(_meetings(), now=now) == 1297
