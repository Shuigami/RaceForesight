from datetime import datetime, timezone

from app.predictions.compare import compute_integrity_status, compute_lock_status


def test_pre_race_clean() -> None:
    lock = compute_lock_status(
        first_saved_at="2026-10-20T12:00:00Z",
        saved_at="2026-10-20T12:00:00Z",
        race_start_at="2026-10-25T19:00:00Z",
        now=datetime(2026, 10, 26, tzinfo=timezone.utc),
    )
    assert lock == "locked_before_start"
    assert (
        compute_integrity_status(
            lock_status=lock,
            race_start_at="2026-10-25T19:00:00Z",
            model_trained_ats=["2026-10-15T10:00:00Z", "2026-10-15T11:00:00Z"],
        )
        == "pre_race"
    )


def test_train_overlap_beats_pre_race_save() -> None:
    lock = compute_lock_status(
        first_saved_at="2026-10-20T12:00:00Z",
        saved_at="2026-10-20T12:00:00Z",
        race_start_at="2026-10-25T19:00:00Z",
        now=datetime(2026, 10, 26, tzinfo=timezone.utc),
    )
    assert (
        compute_integrity_status(
            lock_status=lock,
            race_start_at="2026-10-25T19:00:00Z",
            model_trained_ats=["2026-10-15T10:00:00Z", "2026-10-26T08:00:00Z"],
        )
        == "train_overlap"
    )


def test_post_race_save() -> None:
    lock = compute_lock_status(
        first_saved_at="2026-10-26T12:00:00Z",
        saved_at="2026-10-26T12:00:00Z",
        race_start_at="2026-10-25T19:00:00Z",
        now=datetime(2026, 10, 27, tzinfo=timezone.utc),
    )
    assert lock == "saved_after_start"
    assert (
        compute_integrity_status(
            lock_status=lock,
            race_start_at="2026-10-25T19:00:00Z",
            model_trained_ats=["2026-10-15T10:00:00Z"],
        )
        == "post_race"
    )


def test_missing_trained_at_ignored() -> None:
    assert (
        compute_integrity_status(
            lock_status="locked_before_start",
            race_start_at="2026-10-25T19:00:00Z",
            model_trained_ats=[None, None],
        )
        == "pre_race"
    )
