"""Dedicated race-duration predictions for the Race time tab."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from app.config import settings
from app.domain.models import ClassificationResponse, PredictedFinish
from app.models.lap_time import LapTimeModel
from app.models.race_time import RaceTimeModel
from app.simulation.form import shrunk_pace_offsets
from app.simulation.strategy import StrategySimulator


class RaceTimePredictor:
    """Predict total race duration per driver (not finishing order, not tyre plans)."""

    VERSION = RaceTimeModel.VERSION

    def __init__(self, simulator: StrategySimulator | None = None) -> None:
        self.simulator = simulator or StrategySimulator()
        self.owns_simulator = simulator is None
        self.model = RaceTimeModel()

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
            pace_frame = pace_frame[pace_frame["session_key"].astype(int) != int(race_sk)]

        grid = pipeline.qualifying_grid(meeting.meeting_key)
        history = pipeline.race_results_history(
            years=[y for y in range(2023, settings.default_season + 1)],
            exclude_session_key=race_sk,
            max_sessions=80,
        )
        rainfall = self._session_rainfall(meeting.meeting_key)

        features = self.model.build_race_features(
            drivers=drivers,
            grid=grid,
            history=history,
            pace_frame=pace_frame,
            circuit=circuit,
            rainfall=rainfall,
            race_laps=meeting.race_laps,
            pit_loss=pit_loss,
        )

        if self.model.is_ready:
            if self.model.model is None:
                self.model.load()
            ordered = self.model.predict(features)
            standings = self._standings_from_model(ordered)
            note = (
                "Race durations from dedicated XGBoost race-time model "
                "(grid + form + pace + distance). Not Classification order or Strategy tyre times."
            )
            version = self.VERSION
        else:
            offsets = shrunk_pace_offsets(pace_frame, drivers, circuit)
            lap_model = self.simulator.model
            if lap_model.model is None and lap_model.is_ready:
                lap_model.load()
            baseline = (
                lap_model._baseline_for(circuit)
                if isinstance(lap_model, LapTimeModel) and lap_model.is_ready
                else float(LapTimeModel().circuit_baselines.get(circuit, 98.5))
            )
            standings = self._standings_from_pace(drivers, offsets, meeting.race_laps, baseline, pit_loss)
            note = (
                "Race-time model not trained yet — showing pace×distance fallback. "
                "Run: python scripts/train_race_time.py"
            )
            version = "race-time-pace-fallback-v1"

        return ClassificationResponse(
            meeting=meeting,
            standings=standings,
            model_version=version,
            generated_at=datetime.now(timezone.utc).isoformat(),
            note=note,
        )

    def _standings_from_model(self, ordered: pd.DataFrame) -> list[PredictedFinish]:
        out: list[PredictedFinish] = []
        leader = float(ordered.iloc[0]["predicted_race_time_s"]) if len(ordered) else 0.0
        for _, row in ordered.iterrows():
            race_time = float(row["predicted_race_time_s"])
            out.append(
                PredictedFinish(
                    position=int(row["position"]),
                    driver_number=int(row["driver_number"]),
                    name_acronym=str(row.get("name_acronym") or f"D{row['driver_number']}"),
                    full_name=str(row.get("full_name") or "Unknown"),
                    team_name=str(row.get("team_name") or "Unknown"),
                    team_colour=str(row["team_colour"]) if row.get("team_colour") else None,
                    estimated_race_time_s=round(race_time, 3),
                    gap_to_leader_s=round(race_time - leader, 3),
                    strategy_label="race-time model",
                    confidence=None,
                )
            )
        return out

    def _standings_from_pace(
        self,
        drivers: pd.DataFrame,
        offsets: dict[int, float],
        race_laps: int,
        baseline: float,
        pit_loss: float,
    ) -> list[PredictedFinish]:
        rows: list[tuple[float, dict]] = []
        for _, row in drivers.iterrows():
            dnum = int(row["driver_number"])
            race_time = (baseline + offsets.get(dnum, 0.0)) * race_laps + pit_loss
            rows.append((race_time, row.to_dict()))
        rows.sort(key=lambda x: x[0])
        leader = rows[0][0] if rows else 0.0
        out: list[PredictedFinish] = []
        for idx, (race_time, driver) in enumerate(rows, start=1):
            out.append(
                PredictedFinish(
                    position=idx,
                    driver_number=int(driver["driver_number"]),
                    name_acronym=str(driver.get("name_acronym") or f"D{driver['driver_number']}"),
                    full_name=str(driver.get("full_name") or "Unknown"),
                    team_name=str(driver.get("team_name") or "Unknown"),
                    team_colour=str(driver["team_colour"]) if driver.get("team_colour") else None,
                    estimated_race_time_s=round(race_time, 3),
                    gap_to_leader_s=round(race_time - leader, 3),
                    strategy_label="pace×distance fallback",
                    confidence=None,
                )
            )
        return out
