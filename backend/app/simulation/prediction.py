"""Phase 2 — predicted finishing order (pace ranking, independent of strategy search)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.domain.models import ClassificationResponse, MeetingSummary, PredictedFinish
from app.models.lap_time import LapTimeModel
from app.simulation.strategy import StrategySimulator


class ClassificationPredictor:
    """Predict finishing order from relative race pace — not from optimal tyre strategies.

    Strategy page answers: which tyre plan is fastest for each driver?
    This page answers: who is likely to finish ahead of whom, assuming a shared
    typical dry race shape (baseline lap + driver pace offset + one stop).

    Those are related inputs (both use OpenF1 pace history) but different questions,
    so estimated times here will NOT match Strategy's per-driver optimal race times.
    """

    VERSION = "ranking-pace-v1"

    def __init__(self, simulator: StrategySimulator | None = None) -> None:
        self.simulator = simulator or StrategySimulator()
        self.owns_simulator = simulator is None

    def close(self) -> None:
        if self.owns_simulator:
            self.simulator.close()

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
        offsets = self.simulator._pace_offsets(drivers, circuit)

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
        )
        return ClassificationResponse(
            meeting=meeting,
            standings=standings,
            model_version=self.VERSION,
            generated_at=datetime.now(timezone.utc).isoformat(),
            note=(
                "Finishing order from relative pace (shared 1-stop race shape) — "
                "not a re-sort of Strategy optimal tyre times. Estimated times are secondary."
            ),
        )

    def predict_lightweight(
        self,
        meeting: MeetingSummary,
        drivers_df,
        *,
        pace_offsets: dict[int, float],
        pit_loss: float,
        circuit_baseline: float,
    ) -> list[PredictedFinish]:
        """Rank by typical race pace: circuit baseline + driver offset + one pit stop."""
        rows: list[tuple[float, dict]] = []
        for _, row in drivers_df.iterrows():
            driver = row.to_dict()
            dnum = int(driver["driver_number"])
            race_time = (circuit_baseline + pace_offsets.get(dnum, 0.0)) * meeting.race_laps + pit_loss
            rows.append((race_time, driver))
        rows.sort(key=lambda x: x[0])
        leader = rows[0][0] if rows else 0.0
        n = max(len(rows), 1)
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
                    strategy_label="pace model · shared 1-stop",
                    confidence=round(max(0.35, 1.0 - (idx - 1) / (n * 1.35)), 3),
                )
            )
        return out
