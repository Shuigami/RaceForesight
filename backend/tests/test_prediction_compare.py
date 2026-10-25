from datetime import datetime, timezone

from app.predictions.compare import (
    classification_metrics,
    compounds_match,
    compute_lock_status,
    strategy_metrics,
)


def test_lock_before_start() -> None:
    status = compute_lock_status(
        first_saved_at="2026-10-20T12:00:00Z",
        saved_at="2026-10-20T12:00:00Z",
        race_start_at="2026-10-25T20:00:00Z",
        now=datetime(2026, 10, 26, tzinfo=timezone.utc),
    )
    assert status == "locked_before_start"


def test_lock_awaiting_race() -> None:
    status = compute_lock_status(
        first_saved_at="2026-10-20T12:00:00Z",
        saved_at="2026-10-20T12:00:00Z",
        race_start_at="2026-10-25T20:00:00Z",
        now=datetime(2026, 10, 24, tzinfo=timezone.utc),
    )
    assert status == "awaiting_race_start"


def test_lock_overwritten_after_start() -> None:
    status = compute_lock_status(
        first_saved_at="2026-10-20T12:00:00Z",
        saved_at="2026-10-25T22:00:00Z",
        race_start_at="2026-10-25T20:00:00Z",
        now=datetime(2026, 10, 26, tzinfo=timezone.utc),
    )
    assert status == "overwritten_after_start"


def test_lock_saved_after_start() -> None:
    status = compute_lock_status(
        first_saved_at="2026-10-26T10:00:00Z",
        saved_at="2026-10-26T10:00:00Z",
        race_start_at="2026-10-25T20:00:00Z",
        now=datetime(2026, 10, 26, tzinfo=timezone.utc),
    )
    assert status == "saved_after_start"


def test_compounds_match_order_independent() -> None:
    assert compounds_match(["SOFT", "HARD"], ["HARD", "SOFT"])
    assert not compounds_match(["SOFT", "HARD"], ["MEDIUM", "HARD"])


def test_classification_metrics_top3() -> None:
    pred = [
        {"driver_number": 1, "position": 1},
        {"driver_number": 2, "position": 2},
        {"driver_number": 3, "position": 3},
        {"driver_number": 4, "position": 4},
    ]
    actual = {1: 2, 2: 1, 3: 3, 4: 5}
    m = classification_metrics(pred, actual)
    assert m["n"] == 4
    assert m["top3_hits"] == 3
    assert m["spearman"] is not None


def test_strategy_metrics_rate() -> None:
    pred = [
        {"driver_number": 1, "compounds": ["SOFT", "HARD"]},
        {"driver_number": 2, "compounds": ["MEDIUM", "HARD"]},
    ]
    actual = {1: ["HARD", "SOFT"], 2: ["SOFT", "HARD"]}
    m = strategy_metrics(pred, actual)
    assert m["compound_matches"] == 1
    assert m["compound_match_rate"] == 0.5
