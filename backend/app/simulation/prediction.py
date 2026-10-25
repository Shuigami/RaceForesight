"""Phase 2 — predicted finishing order (pairwise ranker + pace/grid/form features)."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from app.config import settings
from app.domain.models import ClassificationResponse, MeetingSummary, PredictedFinish
from app.models.lap_time import LapTimeModel
from app.models.ranking import RankingModel
from app.simulation.form import shrunk_pace_offsets
from app.simulation.strategy import StrategySimulator


class ClassificationPredictor:
    """Predict finishing order from grid, form and pace — not from optimal tyre strategies.

    Strategy page answers: which tyre plan is fastest for each driver?
    This page answers: who is likely to finish ahead of whom.
    """

    VERSION = "ranking-pairwise-v1"

    def __init__(self, simulator: StrategySimulator | None = None) -> None:
        self.simulator = simulator or StrategySimulator()
        self.owns_simulator = simulator is None
        self.ranker = RankingModel()

    def close(self) -> None:
        if self.owns_simulator:
            self.simulator.close()

    def _session_rainfall(self, meeting_key: int) -> float:
        sk = self.simulator.pipeline.race_session_key(meeting_key)
        if not sk:
            return 0.0
        weather = self.simulator.pipeline.ingest_session(sk).get("weather", pd.DataFrame())
        if weather.empty or "rainfall" not in weather.columns:
            return 0.0
        return float(weather["rainfall"].mean())

    def predict(self, meeting_key: int | None = None) -> ClassificationResponse:
        pipeline = self.simulator.pipeline
        meeting = pipeline.get_meeting(meeting_key)
        drivers = pipeline.drivers_for_meeting(meeting.meeting_key)
        if drivers.empty:
            raise RuntimeError("No drivers found for meeting")
        drivers = drivers.drop_duplicates(subset=["driver_number"])
        if "team_name" in drivers.columns:
            drivers = drivers[drivers["team_name"].notna()]

        circuit = meeting.circuit_short_name or "COTA"
        pit_loss = pipeline.estimate_pit_loss(circuit_short_name=circuit)
        race_sk = pipeline.race_session_key(meeting.meeting_key)
        pace_frame = pipeline.build_training_frame(
            years=[settings.default_season, settings.default_season - 1, settings.default_season - 2],
            max_sessions=40,
            completed_only=True,
        )
        if race_sk and not pace_frame.empty and "session_key" in pace_frame.columns:
            # Avoid leaking the race we are predicting when results already exist
            pace_frame = pace_frame[pace_frame["session_key"].astype(int) != int(race_sk)]

        offsets = shrunk_pace_offsets(pace_frame, drivers, circuit)
        grid = pipeline.qualifying_grid(meeting.meeting_key)
        history = pipeline.race_results_history(
            years=[y for y in range(2023, settings.default_season + 1)],
            exclude_session_key=race_sk,
            max_sessions=80,
        )
        rainfall = self._session_rainfall(meeting.meeting_key)

        features = self.ranker.build_race_features(
            drivers=drivers,
            grid=grid,
            history=history,
            pace_frame=pace_frame,
            circuit=circuit,
            rainfall=rainfall,
        )

        if self.ranker.is_ready:
            if self.ranker.model is None:
                self.ranker.load()
            ordered = self.ranker.predict_order(features)
            standings = self._standings_from_ranker(ordered, meeting, pit_loss, offsets)
            note = (
                "Finishing order from pairwise ranker (grid + form + pace). "
                "Not a re-sort of Strategy optimal tyre times."
            )
            version = self.VERSION
        else:
            lap_model = self.simulator.model
            if lap_model.model is None and lap_model.is_ready:
                lap_model.load()
            baseline = (
                lap_model._baseline_for(circuit)
                if isinstance(lap_model, LapTimeModel) and lap_model.is_ready
                else float(LapTimeModel().circuit_baselines.get(circuit, 98.5))
            )
            standings = self.predict_lightweight(
                meeting,
                drivers,
                pace_offsets=offsets,
                pit_loss=pit_loss,
                circuit_baseline=baseline,
                grid=grid,
            )
            note = (
                "Finishing order from pace+grid heuristic (ranker not trained yet). "
                "Run: python scripts/train_ranker.py"
            )
            version = "ranking-pace-grid-v1"

        return ClassificationResponse(
            meeting=meeting,
            standings=standings,
            model_version=version,
            generated_at=datetime.now(timezone.utc).isoformat(),
            note=note,
        )

    def _standings_from_ranker(
        self,
        ordered: pd.DataFrame,
        meeting: MeetingSummary,
        pit_loss: float,
        offsets: dict[int, float],
    ) -> list[PredictedFinish]:
        lap_model = self.simulator.model
        if lap_model.model is None and lap_model.is_ready:
            lap_model.load()
        circuit = meeting.circuit_short_name or "COTA"
        baseline = (
            lap_model._baseline_for(circuit)
            if isinstance(lap_model, LapTimeModel) and lap_model.is_ready
            else 90.0
        )
        out: list[PredictedFinish] = []
        n = max(len(ordered), 1)
        leader_time = None
        for _, row in ordered.iterrows():
            dnum = int(row["driver_number"])
            race_time = (baseline + offsets.get(dnum, 0.0)) * meeting.race_laps + pit_loss
            if leader_time is None:
                leader_time = race_time
            pos = int(row["position"])
            out.append(
                PredictedFinish(
                    position=pos,
                    driver_number=dnum,
                    name_acronym=str(row.get("name_acronym") or f"D{dnum}"),
                    full_name=str(row.get("full_name") or "Unknown"),
                    team_name=str(row.get("team_name") or "Unknown"),
                    team_colour=str(row["team_colour"]) if row.get("team_colour") else None,
                    headshot_url=(
                        str(row["headshot_url"])
                        if row.get("headshot_url") and str(row.get("headshot_url")) not in ("", "nan", "None")
                        else None
                    ),
                    estimated_race_time_s=round(race_time, 3),
                    gap_to_leader_s=round(race_time - leader_time, 3),
                    strategy_label="ranker · grid+form+pace",
                    confidence=round(max(0.35, 1.0 - (pos - 1) / (n * 1.35)), 3),
                )
            )
        return out

    def predict_lightweight(
        self,
        meeting: MeetingSummary,
        drivers_df,
        *,
        pace_offsets: dict[int, float],
        pit_loss: float,
        circuit_baseline: float,
        grid: dict[int, int] | None = None,
    ) -> list[PredictedFinish]:
        """Fallback: blend grid position with pace-estimated race time."""
        grid = grid or {}
        rows: list[tuple[float, dict]] = []
        n_drivers = max(len(drivers_df), 1)
        for _, row in drivers_df.iterrows():
            driver = row.to_dict()
            dnum = int(driver["driver_number"])
            race_time = (circuit_baseline + pace_offsets.get(dnum, 0.0)) * meeting.race_laps + pit_loss
            grid_pos = grid.get(dnum)
            # Blend: convert grid to a pseudo-time penalty so pole is favoured
            if grid_pos is not None:
                grid_penalty = (grid_pos - 1) * 0.35  # ~0.35s/place over race average signal
                score = 0.55 * race_time + 0.45 * (circuit_baseline * meeting.race_laps + grid_penalty * meeting.race_laps / 20.0)
            else:
                score = race_time + 8.0  # mild penalty if no quali
            rows.append((score, {**driver, "_race_time": race_time}))
        rows.sort(key=lambda x: x[0])
        leader = rows[0][1]["_race_time"] if rows else 0.0
        out: list[PredictedFinish] = []
        for idx, (_, driver) in enumerate(rows, start=1):
            race_time = float(driver["_race_time"])
            out.append(
                PredictedFinish(
                    position=idx,
                    driver_number=int(driver["driver_number"]),
                    name_acronym=str(driver.get("name_acronym") or f"D{driver['driver_number']}"),
                    full_name=str(driver.get("full_name") or "Unknown"),
                    team_name=str(driver.get("team_name") or "Unknown"),
                    team_colour=str(driver["team_colour"]) if driver.get("team_colour") else None,
                    headshot_url=(
                        str(driver["headshot_url"])
                        if driver.get("headshot_url") and str(driver.get("headshot_url")) not in ("", "nan", "None")
                        else None
                    ),
                    estimated_race_time_s=round(race_time, 3),
                    gap_to_leader_s=round(race_time - leader, 3),
                    strategy_label="pace+grid heuristic",
                    confidence=round(max(0.35, 1.0 - (idx - 1) / (n_drivers * 1.35)), 3),
                )
            )
        return out
