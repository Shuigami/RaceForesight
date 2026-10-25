import json
from pathlib import Path

import app.predictions.store as store


def _patch_dir(monkeypatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(store, "predictions_dir", lambda: tmp_path)
    return tmp_path


def _sample_payload(**overrides):
    base = {
        "meeting": {
            "meeting_key": 1001,
            "meeting_name": "Test GP",
            "circuit_short_name": "TST",
            "country_name": "Test",
            "year": 2026,
            "date_start": "2026-03-01T14:00:00Z",
            "is_default": False,
            "race_laps": 57,
        },
        "race_start_at": "2026-03-01T14:00:00Z",
        "first_saved_at": "2026-02-28T10:00:00Z",
        "saved_at": "2026-02-28T10:00:00Z",
        "model_versions": {
            "classification": "c1",
            "race_time": "r1",
            "strategy": "s1",
        },
        "classification": {"standings": [], "note": ""},
        "race_time": {"standings": [], "note": ""},
        "strategy": {"strategies": []},
    }
    base.update(overrides)
    return base


def test_create_list_rename_delete(monkeypatch, tmp_path: Path) -> None:
    _patch_dir(monkeypatch, tmp_path)

    a = store.create_save(1001, _sample_payload(name="First", saved_at="2026-02-28T10:00:00Z"))
    b = store.create_save(
        1001,
        _sample_payload(name="Second", saved_at="2026-02-28T12:00:00Z", first_saved_at="2026-02-28T12:00:00Z"),
    )
    assert a["id"] != b["id"]
    assert (tmp_path / "1001" / f"{a['id']}.json").exists()

    saves = store.list_saves(1001)
    assert [s["name"] for s in saves] == ["Second", "First"]

    meetings = store.list_meetings()
    assert len(meetings) == 1
    assert meetings[0]["meeting_key"] == 1001
    assert meetings[0]["save_count"] == 2

    renamed = store.rename_save(1001, a["id"], "Renamed")
    assert renamed is not None
    assert renamed["name"] == "Renamed"
    assert store.load_save(1001, a["id"])["name"] == "Renamed"

    assert store.delete_save(1001, a["id"]) is True
    assert store.load_save(1001, a["id"]) is None
    assert len(store.list_saves(1001)) == 1

    assert store.delete_save(1001, b["id"]) is True
    assert store.list_saves(1001) == []
    assert store.list_meetings() == []
    assert not (tmp_path / "1001").exists()


def test_migrate_legacy_flat_json(monkeypatch, tmp_path: Path) -> None:
    _patch_dir(monkeypatch, tmp_path)
    legacy = tmp_path / "1297.json"
    legacy.write_text(json.dumps(_sample_payload(meeting={
        "meeting_key": 1297,
        "meeting_name": "Legacy GP",
        "circuit_short_name": "LEG",
        "country_name": "Test",
        "year": 2025,
        "date_start": "2025-05-01T14:00:00Z",
        "is_default": False,
        "race_laps": 50,
    })), encoding="utf-8")

    saves = store.list_saves(1297)
    assert len(saves) == 1
    assert saves[0]["name"] == "Original save"
    assert not legacy.exists()
    assert (tmp_path / "1297" / f"{saves[0]['id']}.json").exists()

    meetings = store.list_meetings()
    assert meetings[0]["meeting_key"] == 1297
    assert meetings[0]["save_count"] == 1


def test_list_meetings_newest_race_first(monkeypatch, tmp_path: Path) -> None:
    _patch_dir(monkeypatch, tmp_path)
    store.create_save(
        1,
        _sample_payload(
            meeting={
                "meeting_key": 1,
                "meeting_name": "Older",
                "circuit_short_name": "OLD",
                "country_name": "Test",
                "year": 2025,
                "date_start": "2025-01-01T12:00:00Z",
                "is_default": False,
                "race_laps": 50,
            },
            race_start_at="2025-01-01T12:00:00Z",
        ),
    )
    store.create_save(
        2,
        _sample_payload(
            meeting={
                "meeting_key": 2,
                "meeting_name": "Newer",
                "circuit_short_name": "NEW",
                "country_name": "Test",
                "year": 2026,
                "date_start": "2026-06-01T12:00:00Z",
                "is_default": False,
                "race_laps": 50,
            },
            race_start_at="2026-06-01T12:00:00Z",
        ),
    )
    meetings = store.list_meetings()
    assert [m["meeting_key"] for m in meetings] == [2, 1]
