from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import settings


def predictions_dir() -> Path:
    path = Path(settings.predictions_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def snapshot_path(meeting_key: int) -> Path:
    return predictions_dir() / f"{int(meeting_key)}.json"


def load_snapshot(meeting_key: int) -> dict[str, Any] | None:
    path = snapshot_path(meeting_key)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_snapshot(meeting_key: int, payload: dict[str, Any]) -> dict[str, Any]:
    path = snapshot_path(meeting_key)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def list_snapshots() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in sorted(predictions_dir().glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        meeting = data.get("meeting") or {}
        out.append(
            {
                "meeting_key": int(meeting.get("meeting_key") or path.stem),
                "meeting_name": meeting.get("meeting_name") or path.stem,
                "year": meeting.get("year"),
                "circuit_short_name": meeting.get("circuit_short_name"),
                "first_saved_at": data.get("first_saved_at"),
                "saved_at": data.get("saved_at"),
                "race_start_at": data.get("race_start_at"),
            }
        )
    return out
