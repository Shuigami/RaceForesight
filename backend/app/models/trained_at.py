"""Training timestamps for model artifacts."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_trained_at(meta: dict, model_path: Path) -> str | None:
    """Prefer meta.trained_at; else joblib mtime so older artifacts still show a date."""
    raw = meta.get("trained_at")
    if raw:
        return str(raw)
    if model_path.exists():
        return (
            datetime.fromtimestamp(model_path.stat().st_mtime, tz=timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
    return None
