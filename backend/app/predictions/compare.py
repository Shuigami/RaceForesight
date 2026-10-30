from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

import numpy as np
from scipy.stats import spearmanr

from app.models.race_time import normalize_race_duration_s

LockStatus = Literal[
    "locked_before_start",
    "overwritten_after_start",
    "saved_after_start",
    "awaiting_race_start",
]

IntegrityStatus = Literal[
    "pre_race",
    "post_race",
    "train_overlap",
    "awaiting_race",
    "unknown",
]


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def compute_lock_status(
    *,
    first_saved_at: str | None,
    saved_at: str | None,
    race_start_at: str | None,
    now: datetime | None = None,
) -> LockStatus:
    now = now or datetime.now(timezone.utc)
    first = _parse_dt(first_saved_at)
    saved = _parse_dt(saved_at) or first
    start = _parse_dt(race_start_at)
    if first is None or start is None:
        return "saved_after_start"
    if first >= start:
        return "saved_after_start"
    if saved is not None and saved >= start:
        return "overwritten_after_start"
    if start > now:
        return "awaiting_race_start"
    return "locked_before_start"


def compute_integrity_status(
    *,
    lock_status: LockStatus,
    race_start_at: str | None,
    model_trained_ats: list[str | None],
) -> IntegrityStatus:
    """Score honesty: train-after-race wins over save timing."""
    start = _parse_dt(race_start_at)
    if start is not None:
        for raw in model_trained_ats:
            trained = _parse_dt(raw)
            if trained is not None and trained >= start:
                return "train_overlap"
    if lock_status == "awaiting_race_start":
        return "awaiting_race"
    if lock_status in ("saved_after_start", "overwritten_after_start"):
        return "post_race"
    if lock_status == "locked_before_start":
        return "pre_race"
    return "unknown"


def compounds_match(pred: list[str] | None, actual: list[str] | None) -> bool:
    if not pred or not actual:
        return False
    return {c.upper() for c in pred} == {c.upper() for c in actual}


def classification_metrics(
    pred_standings: list[dict[str, Any]],
    actual_positions: dict[int, int],
) -> dict[str, float | int | None]:
    pairs: list[tuple[int, int]] = []
    for row in pred_standings:
        dn = int(row["driver_number"])
        if dn not in actual_positions:
            continue
        pairs.append((int(row["position"]), actual_positions[dn]))
    if len(pairs) < 3:
        return {
            "n": len(pairs),
            "spearman": None,
            "top3_hits": 0,
            "mae_pos": None,
        }
    pred_pos = np.array([p[0] for p in pairs], dtype=float)
    true_pos = np.array([p[1] for p in pairs], dtype=float)
    sp = spearmanr(pred_pos, true_pos).correlation
    spearman = float(sp) if sp is not None and not np.isnan(sp) else None
    pred_top3 = {int(row["driver_number"]) for row in pred_standings if int(row["position"]) <= 3}
    actual_top3 = {dn for dn, pos in actual_positions.items() if pos <= 3}
    return {
        "n": len(pairs),
        "spearman": round(spearman, 4) if spearman is not None else None,
        "top3_hits": len(pred_top3 & actual_top3),
        "mae_pos": round(float(np.mean(np.abs(pred_pos - true_pos))), 3),
    }


def race_time_metrics(
    pred_standings: list[dict[str, Any]],
    actual_durations: dict[int, float],
) -> dict[str, float | int | None]:
    errs: list[float] = []
    for row in pred_standings:
        dn = int(row["driver_number"])
        pred = row.get("estimated_race_time_s")
        if pred is None or dn not in actual_durations:
            continue
        errs.append(abs(float(pred) - actual_durations[dn]))
    if not errs:
        return {"n": 0, "mae_s": None, "rmse_s": None}
    arr = np.array(errs, dtype=float)
    return {
        "n": len(errs),
        "mae_s": round(float(arr.mean()), 2),
        "rmse_s": round(float(np.sqrt((arr**2).mean())), 2),
    }


def strategy_metrics(
    pred_strategies: list[dict[str, Any]],
    actual_by_driver: dict[int, list[str]],
) -> dict[str, float | int | None]:
    """Share of the field whose actual compounds match any of the predicted top strategies."""
    pred_sets = [
        {c.upper() for c in (row.get("compounds") or [])}
        for row in pred_strategies
        if row.get("compounds")
    ]
    matched = 0
    n = 0
    for compounds in actual_by_driver.values():
        n += 1
        act = {c.upper() for c in compounds}
        if act and any(act == p for p in pred_sets):
            matched += 1
    return {
        "n": n,
        "compound_matches": matched,
        "compound_match_rate": round(matched / n, 4) if n else None,
    }


def parse_actual_results(session_result_df) -> tuple[dict[int, int], dict[int, float]]:
    """Positions + durations from OpenF1 session_result DataFrame."""
    positions: dict[int, int] = {}
    durations: dict[int, float] = {}
    if session_result_df is None or getattr(session_result_df, "empty", True):
        return positions, durations
    if "position" not in session_result_df.columns or "driver_number" not in session_result_df.columns:
        return positions, durations
    rows = session_result_df.dropna(subset=["position", "driver_number"])
    for _, row in rows.iterrows():
        dn = int(row["driver_number"])
        positions[dn] = int(row["position"])
        if "duration" in session_result_df.columns:
            dur = normalize_race_duration_s(row.get("duration"))
            if dur is not None:
                durations[dn] = dur
    return positions, durations
