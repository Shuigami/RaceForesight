from app.training.jobs import TrainJobManager


def test_start_rejects_second_job(monkeypatch) -> None:
    mgr = TrainJobManager()

    def fake_run(*_args, **_kwargs):
        return None

    monkeypatch.setattr(mgr, "_run", fake_run)
    first = mgr.start(["lap_time"])
    assert first["status"] == "queued"
    assert "lap_time" in first["models"]

    # Simulate still running
    with mgr._lock:
        mgr._job["status"] = "running"

    try:
        mgr.start(["classification"])
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "already running" in str(exc)


def test_status_deepcopy_isolated() -> None:
    mgr = TrainJobManager()
    with mgr._lock:
        mgr._job = {
            "job_id": "abc",
            "status": "running",
            "targets": ["lap_time"],
            "years": [2026],
            "max_sessions": None,
            "started_at": "t0",
            "finished_at": None,
            "error": None,
            "models": {
                "lap_time": {
                    "status": "running",
                    "stage": "pace",
                    "current": 2,
                    "total": 10,
                    "error": None,
                }
            },
        }
    snap = mgr.status()
    assert snap is not None
    snap["models"]["lap_time"]["current"] = 99
    again = mgr.status()
    assert again is not None
    assert again["models"]["lap_time"]["current"] == 2
