from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from app.config import settings


def predictions_dir() -> Path:
    path = Path(settings.predictions_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def meeting_dir(meeting_key: int) -> Path:
    path = predictions_dir() / str(int(meeting_key))
    path.mkdir(parents=True, exist_ok=True)
    return path


def legacy_snapshot_path(meeting_key: int) -> Path:
    return predictions_dir() / f"{int(meeting_key)}.json"


def save_path(meeting_key: int, save_id: str) -> Path:
    return meeting_dir(meeting_key) / f"{save_id}.json"


def _new_save_id() -> str:
    return uuid.uuid4().hex[:12]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def migrate_legacy_meeting(meeting_key: int) -> dict[str, Any] | None:
    """Move `{meeting_key}.json` into `{meeting_key}/{id}.json` if present."""
    legacy = legacy_snapshot_path(meeting_key)
    if not legacy.exists():
        return None
    data = _read_json(legacy)
    if data is None:
        return None
    save_id = str(data.get("id") or _new_save_id())
    data["id"] = save_id
    data.setdefault("name", "Original save")
    target = save_path(meeting_key, save_id)
    _write_json(target, data)
    legacy.unlink(missing_ok=True)
    return data


def ensure_meeting_migrated(meeting_key: int) -> None:
    migrate_legacy_meeting(meeting_key)


def _meeting_keys_on_disk() -> list[int]:
    root = predictions_dir()
    keys: set[int] = set()
    for path in root.iterdir():
        if path.is_file() and path.suffix == ".json" and path.stem.isdigit():
            keys.add(int(path.stem))
        elif path.is_dir() and path.name.isdigit():
            keys.add(int(path.name))
    return sorted(keys)


def list_saves(meeting_key: int) -> list[dict[str, Any]]:
    ensure_meeting_migrated(meeting_key)
    directory = predictions_dir() / str(int(meeting_key))
    if not directory.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for path in directory.glob("*.json"):
        data = _read_json(path)
        if data is None:
            continue
        meeting = data.get("meeting") or {}
        save_id = str(data.get("id") or path.stem)
        out.append(
            {
                "id": save_id,
                "name": data.get("name") or save_id,
                "meeting_key": int(meeting.get("meeting_key") or meeting_key),
                "meeting_name": meeting.get("meeting_name") or str(meeting_key),
                "year": meeting.get("year"),
                "circuit_short_name": meeting.get("circuit_short_name"),
                "circuit_image": meeting.get("circuit_image"),
                "country_flag": meeting.get("country_flag"),
                "first_saved_at": data.get("first_saved_at"),
                "saved_at": data.get("saved_at"),
                "race_start_at": data.get("race_start_at"),
            }
        )
    out.sort(key=lambda item: item.get("saved_at") or "", reverse=True)
    return out


def list_meetings() -> list[dict[str, Any]]:
    """One row per meeting that has at least one save, newest race first."""
    meetings: list[dict[str, Any]] = []
    for key in _meeting_keys_on_disk():
        saves = list_saves(key)
        if not saves:
            continue
        first = min(saves, key=lambda s: s.get("first_saved_at") or s.get("saved_at") or "")
        latest = max(saves, key=lambda s: s.get("saved_at") or "")
        meetings.append(
            {
                "meeting_key": key,
                "meeting_name": latest.get("meeting_name") or str(key),
                "year": latest.get("year"),
                "circuit_short_name": latest.get("circuit_short_name"),
                "circuit_image": latest.get("circuit_image"),
                "country_flag": latest.get("country_flag"),
                "first_saved_at": first.get("first_saved_at") or first.get("saved_at"),
                "saved_at": latest.get("saved_at"),
                "race_start_at": latest.get("race_start_at"),
                "save_count": len(saves),
            }
        )

    def sort_key(item: dict[str, Any]) -> tuple:
        race = item.get("race_start_at") or ""
        year = item.get("year") or 0
        saved = item.get("saved_at") or ""
        return (race, year, saved)

    meetings.sort(key=sort_key, reverse=True)
    return meetings


def load_save(meeting_key: int, save_id: str) -> dict[str, Any] | None:
    ensure_meeting_migrated(meeting_key)
    return _read_json(save_path(meeting_key, save_id))


def create_save(meeting_key: int, payload: dict[str, Any]) -> dict[str, Any]:
    ensure_meeting_migrated(meeting_key)
    save_id = str(payload.get("id") or _new_save_id())
    payload = {**payload, "id": save_id}
    if not payload.get("name"):
        payload["name"] = save_id
    _write_json(save_path(meeting_key, save_id), payload)
    return payload


def rename_save(meeting_key: int, save_id: str, name: str) -> dict[str, Any] | None:
    data = load_save(meeting_key, save_id)
    if data is None:
        return None
    data["name"] = name.strip() or data.get("name") or save_id
    _write_json(save_path(meeting_key, save_id), data)
    return data


def delete_save(meeting_key: int, save_id: str) -> bool:
    ensure_meeting_migrated(meeting_key)
    path = save_path(meeting_key, save_id)
    if not path.exists():
        return False
    path.unlink()
    directory = predictions_dir() / str(int(meeting_key))
    if directory.is_dir() and not any(directory.glob("*.json")):
        try:
            directory.rmdir()
        except OSError:
            pass
    return True
