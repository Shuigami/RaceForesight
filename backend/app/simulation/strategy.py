"""Enumerate and score dry-race tyre strategies for the full grid."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from itertools import combinations

import pandas as pd

from app.config import settings
from app.data.pipeline import RaceDataPipeline
from app.domain.models import (
    DriverStrategy,
    GlobalStrategy,
    MeetingSummary,
    PacePoint,
    StintPaceCurve,
    StintPlan,
    StrategyDetail,
    StrategyOption,
    StrategyResponse,
)
from app.models.lap_time import LapTimeModel

DRY_COMPOUNDS = ("SOFT", "MEDIUM", "HARD")

# Collapse nearby pit samples of the same compound plan into one pit window.
# shortcut: fixed seconds band, retune if windows are too wide/narrow on real races
_PIT_WINDOW_EPS_S = 2.0

# Pace loss per lap of tyre age (s) — used as the primary wear curve.
# Soft wears fastest; hard slowest. Tuned as a clear UI/strategy prior, not a lab curve.
_COMPOUND_WEAR_S_PER_LAP = {
    "SOFT": 0.065,
    "MEDIUM": 0.040,
    "HARD": 0.025,
}


def _shape_key(strat: dict) -> tuple[int, tuple[str, ...]]:
    return (int(strat["stops"]), tuple(str(c).upper() for c in strat["compounds"]))


def _format_pit_windows(windows: list[list[int]]) -> str:
    parts: list[str] = []
    for lo, hi in windows:
        parts.append(f"{lo}-{hi}" if lo != hi else str(lo))
    return ",".join(parts)


def _monotonic_tyre_loss_seconds(raw_effects: list[float], compound: str) -> list[float]:
    """Build a stint wear curve that always grows with tyre age.

    Raw XGBoost tyre deltas are often inverted or noisy (fuel confound). Flipping them
    and taking a running-max locked an early spike for the whole stint (flat chart).

    Instead:
    1) physical wear = rate * laps_into_stint (always increasing),
    2) only add model slowdown when it is *positive* vs fresh (ignore "faster when older"),
    3) running-max so wear never decreases.
    """
    if not raw_effects:
        return []
    anchored = [e - raw_effects[0] for e in raw_effects]
    rate = _COMPOUND_WEAR_S_PER_LAP.get(compound.upper(), 0.03)

    mono: list[float] = []
    running = 0.0
    for i, e in enumerate(anchored):
        physical = rate * i
        # Ignore negative model deltas ("tyre got faster") — those are artefacts
        model_slowdown = max(0.0, e)
        running = max(running, physical, model_slowdown)
        mono.append(running)
    return mono


class StrategySimulator:
    def __init__(
        self,
        pipeline: RaceDataPipeline | None = None,
        model: LapTimeModel | None = None,
    ) -> None:
        self.pipeline = pipeline or RaceDataPipeline()
        self.owns_pipeline = pipeline is None
        self.model = model or LapTimeModel()
        if not self.model.is_ready:
            # Allow deferred load; callers may train first
            pass
        else:
            self.model.load()

    def close(self) -> None:
        if self.owns_pipeline:
            self.pipeline.close()

    def _ensure_model(self) -> None:
        if self.model.model is None:
            if self.model.is_ready:
                self.model.load()
            else:
                raise FileNotFoundError(
                    "Lap-time model not trained. Run: python scripts/train_model.py"
                )

    def _pace_offsets(
        self,
        drivers: pd.DataFrame,
        circuit: str,
        *,
        exclude_session_key: int | None = None,
        years: list[int] | None = None,
        max_sessions: int = 40,
    ) -> dict[int, float]:
        """Calibrate driver pace from recent laps (circuit-preferred, shrunk for newcomers)."""
        from app.simulation.form import shrunk_pace_offsets

        years = years or [settings.default_season, settings.default_season - 1, settings.default_season - 2]
        try:
            train = self.pipeline.build_training_frame(
                years=years,
                max_sessions=max_sessions,
                completed_only=True,
            )
        except Exception:
            train = pd.DataFrame()

        if not train.empty and exclude_session_key is not None and "session_key" in train.columns:
            train = train[train["session_key"].astype(int) != int(exclude_session_key)]

        return shrunk_pace_offsets(train, drivers, circuit)

    def _candidate_strategies(self, total_laps: int) -> list[dict]:
        """1-stop and 2-stop dry strategies with two distinct compounds."""
        strategies: list[dict] = []
        # 1-stop windows around typical COTA first stop
        one_stop_laps = [14, 18, 22, 26, 30, 34]
        one_stop_laps = [max(8, min(total_laps - 8, lap)) for lap in one_stop_laps]
        for c1, c2 in combinations(DRY_COMPOUNDS, 2):
            for order in ((c1, c2), (c2, c1)):
                for pit in one_stop_laps:
                    strategies.append(
                        {
                            "stops": 1,
                            "compounds": list(order),
                            "pit_laps": [pit],
                            "label": f"1-stop {order[0][0]}/{order[1][0]} @{pit}",
                        }
                    )

        # 2-stop: common compound patterns only (keep search tractable for full grid)
        two_stop_patterns = [
            ("SOFT", "MEDIUM", "HARD"),
            ("SOFT", "HARD", "MEDIUM"),
            ("MEDIUM", "HARD", "MEDIUM"),
            ("MEDIUM", "SOFT", "HARD"),
            ("HARD", "MEDIUM", "SOFT"),
            ("HARD", "SOFT", "MEDIUM"),
        ]
        two_stop_windows = [(12, 32), (15, 36), (18, 38), (20, 40), (14, 35)]
        for compounds in two_stop_patterns:
            for p1, p2 in two_stop_windows:
                if p2 >= total_laps - 5 or p2 - p1 < 8:
                    continue
                strategies.append(
                    {
                        "stops": 2,
                        "compounds": list(compounds),
                        "pit_laps": [p1, p2],
                        "label": f"2-stop {'/'.join(c[0] for c in compounds)} @{p1},{p2}",
                    }
                )
        return strategies

    def _stints_from_strategy(self, strategy: dict, total_laps: int) -> list[StintPlan]:
        pits = strategy["pit_laps"]
        compounds = strategy["compounds"]
        boundaries = [1] + [p + 1 for p in pits] + [total_laps + 1]
        stints: list[StintPlan] = []
        for i, compound in enumerate(compounds):
            lap_start = boundaries[i]
            lap_end = boundaries[i + 1] - 1
            if lap_end < lap_start:
                continue
            stints.append(
                StintPlan(
                    compound=compound,
                    lap_start=lap_start,
                    lap_end=lap_end,
                    tyre_age_at_start=0,
                )
            )
        return stints

    def score_strategy(
        self,
        *,
        driver_number: int,
        team_name: str,
        circuit: str,
        total_laps: int,
        strategy: dict,
        pit_loss: float,
        pace_offset: float,
        track_temp: float = 35.0,
    ) -> tuple[float, list[StintPlan]]:
        stints = self._stints_from_strategy(strategy, total_laps)
        total = 0.0
        for stint in stints:
            laps = self.model.predict_stint_laps(
                driver_number=driver_number,
                team_name=team_name,
                circuit_short_name=circuit,
                compound=stint.compound,
                lap_start=stint.lap_start,
                lap_end=stint.lap_end,
                tyre_age_at_start=stint.tyre_age_at_start,
                total_laps=total_laps,
                track_temp=track_temp,
                pace_offset=pace_offset,
            )
            total += sum(laps)
        total += strategy["stops"] * pit_loss
        return total, stints

    def _build_stint_curve(
        self,
        *,
        driver_number: int,
        team_name: str,
        circuit: str,
        stint: StintPlan,
        stint_index: int,
        total_laps: int,
        pace_offset: float,
        track_temp: float,
    ) -> StintPaceCurve:
        """Race-pace points for a stint + tyre-only delta (fuel/lap held fixed)."""
        lap_end = min(stint.lap_end, stint.lap_start + 24)
        preds = self.model.predict_stint_laps(
            driver_number=driver_number,
            team_name=team_name,
            circuit_short_name=circuit,
            compound=stint.compound,
            lap_start=stint.lap_start,
            lap_end=lap_end,
            tyre_age_at_start=stint.tyre_age_at_start,
            total_laps=total_laps,
            track_temp=track_temp,
            pace_offset=pace_offset,
        )

        # Isolate tyre wear: same mid-stint fuel/lap, only tyre_age varies
        mid_lap = (stint.lap_start + lap_end) // 2
        mid_fuel = max(1, total_laps - mid_lap + 1)
        ages = list(range(stint.tyre_age_at_start, stint.tyre_age_at_start + len(preds)))
        tyre_only_rows = [
            {
                "driver_number": driver_number,
                "team_name": team_name,
                "circuit_short_name": circuit,
                "compound": stint.compound,
                "tyre_age": age,
                "lap_number": mid_lap,
                "fuel_proxy": mid_fuel,
                "track_temp": track_temp,
                "rainfall": 0.0,
            }
            for age in ages
        ]
        tyre_preds = self.model.predict_laps(pd.DataFrame(tyre_only_rows))
        tyre_base = float(tyre_preds[0]) if len(tyre_preds) else 0.0
        raw_effects = [float(p) - tyre_base for p in tyre_preds]
        wear_effects = _monotonic_tyre_loss_seconds(raw_effects, stint.compound)
        # Typical soft/medium/hard stint horizon for "life used" percentage
        life_horizon = max(len(preds) - 1, 1)

        points: list[PacePoint] = []
        for i, pred in enumerate(preds):
            lap_number = stint.lap_start + i
            tyre_age = stint.tyre_age_at_start + i
            effect_s = wear_effects[i] if i < len(wear_effects) else 0.0
            deg_pct = (effect_s / tyre_base * 100.0) if tyre_base else 0.0
            life_used = (i / life_horizon) * 100.0
            points.append(
                PacePoint(
                    lap_number=lap_number,
                    tyre_age=tyre_age,
                    fuel_proxy=max(1, total_laps - lap_number + 1),
                    predicted_lap_s=round(float(pred), 3),
                    tyre_effect_s=round(effect_s, 3),
                    tyre_degradation_pct=round(deg_pct, 3),
                    tyre_life_used_pct=round(life_used, 2),
                    compound=stint.compound,
                )
            )
        return StintPaceCurve(
            stint_index=stint_index,
            compound=stint.compound,
            lap_start=stint.lap_start,
            lap_end=lap_end,
            points=points,
        )

    def simulate_driver(
        self,
        *,
        driver: dict,
        meeting: MeetingSummary,
        pit_loss: float,
        pace_offset: float,
        top_n: int = 5,
        track_temp: float = 35.0,
    ) -> tuple[
        DriverStrategy,
        list[DriverStrategy],
        list[dict],
        list[StintPaceCurve],
        list[StrategyOption],
    ]:
        self._ensure_model()
        total_laps = meeting.race_laps
        circuit = meeting.circuit_short_name or "COTA"
        candidates = self._candidate_strategies(total_laps)

        scored: list[tuple[float, dict, list[StintPlan]]] = []
        for strat in candidates:
            race_time, stints = self.score_strategy(
                driver_number=int(driver["driver_number"]),
                team_name=str(driver.get("team_name") or "Unknown"),
                circuit=circuit,
                total_laps=total_laps,
                strategy=strat,
                pit_loss=pit_loss,
                pace_offset=pace_offset,
                track_temp=track_temp,
            )
            scored.append((race_time, strat, stints))

        scored.sort(key=lambda x: x[0])
        best_time, best_strat, best_stints = scored[0]

        def to_ds(race_time: float, strat: dict, stints: list[StintPlan]) -> DriverStrategy:
            return DriverStrategy(
                driver_number=int(driver["driver_number"]),
                name_acronym=str(driver.get("name_acronym") or f"D{driver['driver_number']}"),
                full_name=str(driver.get("full_name") or driver.get("broadcast_name") or "Unknown"),
                team_name=str(driver.get("team_name") or "Unknown"),
                team_colour=str(driver["team_colour"]) if driver.get("team_colour") else None,
                stops=int(strat["stops"]),
                compounds=list(strat["compounds"]),
                pit_laps=list(strat["pit_laps"]),
                stints=stints,
                predicted_race_time_s=round(race_time, 3),
                predicted_avg_lap_s=round(race_time / total_laps, 3),
                strategy_label=str(strat["label"]),
            )

        ranked = [to_ds(t, s, st) for t, s, st in scored[:top_n]]
        best = ranked[0]
        alternatives = ranked[1:]

        def curves_for(ds: DriverStrategy) -> list[StintPaceCurve]:
            return [
                self._build_stint_curve(
                    driver_number=ds.driver_number,
                    team_name=ds.team_name,
                    circuit=circuit,
                    stint=stint,
                    stint_index=i,
                    total_laps=total_laps,
                    pace_offset=pace_offset,
                    track_temp=track_temp,
                )
                for i, stint in enumerate(ds.stints)
            ]

        options = [
            StrategyOption(
                strategy=ds,
                stint_curves=curves_for(ds),
                is_recommended=(i == 0),
            )
            for i, ds in enumerate(ranked)
        ]
        stint_curves = options[0].stint_curves if options else []
        # Legacy flat curve = first stint race-pace points of recommended strategy
        deg = [
            {
                "tyre_age": p.tyre_age,
                "predicted_lap_s": p.predicted_lap_s,
                "compound": p.compound,
                "lap_number": p.lap_number,
                "fuel_proxy": p.fuel_proxy,
                "tyre_effect_s": p.tyre_effect_s,
                "tyre_degradation_pct": p.tyre_degradation_pct,
                "tyre_life_used_pct": p.tyre_life_used_pct,
            }
            for p in (stint_curves[0].points if stint_curves else [])
        ]

        return best, alternatives, deg, stint_curves, options

    def _to_global_strategies(
        self,
        scored: list[tuple[float, dict, list[StintPlan]]],
        total_laps: int,
        top_n: int,
    ) -> list[GlobalStrategy]:
        """Rank by compound plan; merge pit-lap samples into competitive windows."""
        if not scored:
            return []

        by_shape: dict[tuple[int, tuple[str, ...]], list[tuple[float, dict, list[StintPlan]]]] = (
            defaultdict(list)
        )
        for item in scored:
            by_shape[_shape_key(item[1])].append(item)

        collapsed: list[tuple[float, dict, list[StintPlan], list[list[int]], str]] = []
        for (_stops, _compounds), items in by_shape.items():
            items_sorted = sorted(items, key=lambda x: x[0])
            best_time, best_strat, best_stints = items_sorted[0]
            near = [it for it in items_sorted if it[0] <= best_time + _PIT_WINDOW_EPS_S]
            n_pits = int(best_strat["stops"])
            windows: list[list[int]] = []
            for i in range(n_pits):
                laps_i = [int(it[1]["pit_laps"][i]) for it in near if len(it[1]["pit_laps"]) > i]
                windows.append([min(laps_i), max(laps_i)])
            compounds = list(best_strat["compounds"])
            label = (
                f"{n_pits}-stop {'/'.join(c[0] for c in compounds)} "
                f"@{_format_pit_windows(windows)}"
            )
            collapsed.append((best_time, best_strat, best_stints, windows, label))

        collapsed.sort(key=lambda x: x[0])
        collapsed = collapsed[:top_n]
        overall_best = collapsed[0][0]
        out: list[GlobalStrategy] = []
        for i, (race_time, strat, stints, windows, label) in enumerate(collapsed):
            out.append(
                GlobalStrategy(
                    rank=i + 1,
                    stops=int(strat["stops"]),
                    compounds=list(strat["compounds"]),
                    pit_laps=list(strat["pit_laps"]),
                    pit_windows=windows,
                    stints=stints,
                    predicted_race_time_s=round(race_time, 3),
                    predicted_avg_lap_s=round(race_time / total_laps, 3) if total_laps else None,
                    strategy_label=label,
                    gap_to_best_s=round(race_time - overall_best, 3),
                )
            )
        return out

    def simulate_grid(self, meeting_key: int | None = None, top_n: int = 4) -> StrategyResponse:
        """Top dry tyre strategies for the race (field-level, not per driver)."""
        self._ensure_model()
        meeting = self.pipeline.get_meeting(meeting_key)
        drivers = self.pipeline.drivers_for_meeting(meeting.meeting_key)
        if drivers.empty:
            raise RuntimeError("No drivers found for meeting")

        drivers = drivers.drop_duplicates(subset=["driver_number"])
        if "team_name" in drivers.columns:
            drivers = drivers[drivers["team_name"].notna()]
        if drivers.empty:
            raise RuntimeError("No drivers found for meeting")

        # Reference car only — pace_offset=0 so ranking is compound/pit shape, not driver pace
        ref = drivers.iloc[0].to_dict()
        pit_loss = self.pipeline.estimate_pit_loss(circuit_short_name=meeting.circuit_short_name or "COTA")
        total_laps = meeting.race_laps
        circuit = meeting.circuit_short_name or "COTA"

        scored: list[tuple[float, dict, list[StintPlan]]] = []
        for strat in self._candidate_strategies(total_laps):
            race_time, stints = self.score_strategy(
                driver_number=int(ref["driver_number"]),
                team_name=str(ref.get("team_name") or "Unknown"),
                circuit=circuit,
                total_laps=total_laps,
                strategy=strat,
                pit_loss=pit_loss,
                pace_offset=0.0,
            )
            scored.append((race_time, strat, stints))

        strategies = self._to_global_strategies(scored, total_laps, top_n)
        actual = self.pipeline.actual_strategies_for_meeting(meeting.meeting_key)
        return StrategyResponse(
            meeting=meeting,
            strategies=strategies,
            actual=actual,
            model_version=self.model.meta.get("version", "xgboost-lap-v1"),
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    def simulate_driver_detail(self, meeting_key: int | None, driver_number: int) -> StrategyDetail:
        meeting = self.pipeline.get_meeting(meeting_key)
        drivers = self.pipeline.drivers_for_meeting(meeting.meeting_key)
        match = drivers[drivers["driver_number"] == driver_number]
        if match.empty:
            raise ValueError(f"Driver {driver_number} not found")
        driver = match.iloc[0].to_dict()
        pit_loss = self.pipeline.estimate_pit_loss(circuit_short_name=meeting.circuit_short_name or "COTA")
        offsets = self._pace_offsets(drivers, meeting.circuit_short_name or "COTA")
        best, alts, deg, stint_curves, options = self.simulate_driver(
            driver=driver,
            meeting=meeting,
            pit_loss=pit_loss,
            pace_offset=offsets.get(int(driver_number), 0.0),
            top_n=6,
        )
        actuals = self.pipeline.actual_strategies_for_meeting(meeting.meeting_key)
        actual = next((a for a in actuals if a.driver_number == int(driver_number)), None)
        return StrategyDetail(
            meeting=meeting,
            best=best,
            alternatives=alts,
            degradation_curve=deg,
            stint_curves=stint_curves,
            options=options,
            actual=actual,
            model_version=self.model.meta.get("version", "xgboost-lap-v1"),
        )
