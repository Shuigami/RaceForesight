"""Driver pace offsets and finishing-form features (no race-result leakage)."""

from __future__ import annotations

import pandas as pd


def shrunk_pace_offsets(
    frame: pd.DataFrame,
    drivers: pd.DataFrame,
    circuit: str,
    *,
    min_laps_full: int = 40,
    prior_strength: float = 25.0,
) -> dict[int, float]:
    """Median lap delta vs field, shrunk toward 0 for newcomers / sparse samples.

    Prefers same-circuit history when enough laps exist; otherwise uses recent races.
    """
    driver_nums = [int(d) for d in drivers["driver_number"].tolist()]
    offsets = {d: 0.0 for d in driver_nums}
    n_samples = {d: 0 for d in driver_nums}
    if frame.empty or "lap_duration" not in frame.columns:
        return offsets

    same = frame[frame["circuit_short_name"].astype(str).str.upper() == circuit.upper()]
    use = same if len(same) > 200 else frame
    field = float(use["lap_duration"].median())

    for driver_number, grp in use.groupby("driver_number"):
        d = int(driver_number)
        n = int(len(grp))
        raw = float(grp["lap_duration"].median()) - field
        # Empirical Bayes shrink toward field (offset 0)
        weight = n / (n + prior_strength)
        offsets[d] = weight * raw
        n_samples[d] = n

    for d in driver_nums:
        offsets.setdefault(d, 0.0)
        # Extra shrink if below full-confidence sample size
        n = n_samples.get(d, 0)
        if 0 < n < min_laps_full:
            offsets[d] *= n / min_laps_full
    return offsets


def finishing_form(
    history: pd.DataFrame,
    driver_number: int,
    *,
    circuit: str | None = None,
    last_n: int = 5,
) -> tuple[float, int]:
    """Average finish position over recent races (optionally same circuit). Higher = worse."""
    if history.empty:
        return 10.5, 0
    hist = history[history["driver_number"].astype(int) == int(driver_number)].copy()
    if hist.empty:
        return 10.5, 0
    hist = hist.sort_values("date_start")
    if circuit:
        same = hist[hist["circuit_short_name"].astype(str).str.upper() == circuit.upper()]
        pool = same if not same.empty else hist
    else:
        pool = hist
    tail = pool.tail(last_n)
    return float(tail["position"].mean()), int(len(tail))


def team_form(history: pd.DataFrame, team_drivers: list[int], *, last_n: int = 5) -> float:
    if history.empty or not team_drivers:
        return 10.5
    vals = []
    for d in team_drivers:
        avg, n = finishing_form(history, d, last_n=last_n)
        if n > 0:
            vals.append(avg)
    return float(sum(vals) / len(vals)) if vals else 10.5
