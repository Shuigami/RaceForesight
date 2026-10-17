"""Enumerate and score dry-race tyre strategies for the full grid."""

from __future__ import annotations

from datetime import datetime, timezone
from itertools import combinations

import pandas as pd

from app.config import settings
from app.data.pipeline import RaceDataPipeline
from app.domain.models import (
    DriverStrategy,
    MeetingSummary,
    StintPlan,
    StrategyDetail,
    StrategyResponse,
)
from app.models.lap_time import LapTimeModel

DRY_COMPOUNDS = ("SOFT", "MEDIUM", "HARD")


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

    def _pace_offsets(self, drivers: pd.DataFrame, circuit: str) -> dict[int, float]:
        """Calibrate driver pace from recent race lap averages vs field."""
        offsets: dict[int, float] = {}
        try:
            train = self.pipeline.build_training_frame(
                years=[settings.default_season, settings.default_season - 1, settings.default_season - 2],
                max_sessions=12,
            )
        except Exception:
            train = pd.DataFrame()

        if train.empty or "lap_duration" not in train.columns:
            return {int(d): 0.0 for d in drivers["driver_number"].tolist()}

        recent = train.copy()
        # Prefer same circuit when available
        same = recent[recent["circuit_short_name"].astype(str).str.upper() == circuit.upper()]
        use = same if len(same) > 200 else recent
        field = float(use["lap_duration"].median())
        for driver_number, grp in use.groupby("driver_number"):
            driver_med = float(grp["lap_duration"].median())
            offsets[int(driver_number)] = driver_med - field
        for d in drivers["driver_number"].tolist():
            offsets.setdefault(int(d), 0.0)
        return offsets

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

    def simulate_driver(
        self,
        *,
        driver: dict,
        meeting: MeetingSummary,
        pit_loss: float,
        pace_offset: float,
        top_n: int = 5,
        track_temp: float = 35.0,
    ) -> tuple[DriverStrategy, list[DriverStrategy], list[dict]]:
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

        best = to_ds(best_time, best_strat, best_stints)
        alternatives = [to_ds(t, s, st) for t, s, st in scored[1:top_n]]

        # Degradation curve for best first stint compound
        deg: list[dict] = []
        first = best.stints[0]
        preds = self.model.predict_stint_laps(
            driver_number=best.driver_number,
            team_name=best.team_name,
            circuit_short_name=circuit,
            compound=first.compound,
            lap_start=1,
            lap_end=min(25, total_laps),
            tyre_age_at_start=0,
            total_laps=total_laps,
            track_temp=track_temp,
            pace_offset=pace_offset,
        )
        for i, p in enumerate(preds, start=1):
            deg.append({"tyre_age": i - 1, "predicted_lap_s": round(p, 3), "compound": first.compound})

        return best, alternatives, deg

    def simulate_grid(self, meeting_key: int | None = None, top_n: int = 3) -> StrategyResponse:
        meeting = self.pipeline.get_meeting(meeting_key)
        drivers = self.pipeline.drivers_for_meeting(meeting.meeting_key)
        if drivers.empty:
            raise RuntimeError("No drivers found for meeting")

        # Limit to 20 entries (current grid)
        drivers = drivers.drop_duplicates(subset=["driver_number"]).head(20)
        pit_loss = self.pipeline.estimate_pit_loss(circuit_short_name=meeting.circuit_short_name or "COTA")
        offsets = self._pace_offsets(drivers, meeting.circuit_short_name or "COTA")

        results: list[DriverStrategy] = []
        for _, row in drivers.iterrows():
            driver = row.to_dict()
            best, _, _ = self.simulate_driver(
                driver=driver,
                meeting=meeting,
                pit_loss=pit_loss,
                pace_offset=offsets.get(int(driver["driver_number"]), 0.0),
                top_n=top_n,
            )
            results.append(best)

        results.sort(key=lambda d: d.predicted_race_time_s)
        return StrategyResponse(
            meeting=meeting,
            drivers=results,
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
        best, alts, deg = self.simulate_driver(
            driver=driver,
            meeting=meeting,
            pit_loss=pit_loss,
            pace_offset=offsets.get(int(driver_number), 0.0),
            top_n=6,
        )
        return StrategyDetail(
            meeting=meeting,
            best=best,
            alternatives=alts,
            degradation_curve=deg,
            model_version=self.model.meta.get("version", "xgboost-lap-v1"),
        )
