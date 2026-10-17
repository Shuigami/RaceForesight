"""Phase 2 — predicted finishing order (classification first, times secondary)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.domain.models import ClassificationResponse, MeetingSummary, PredictedFinish, StrategyResponse
from app.simulation.strategy import StrategySimulator


class ClassificationPredictor:
    """Rank the grid from strategy race-time simulation.

    Position order is the product; estimated times are supporting detail only.
    """

    def __init__(self, simulator: StrategySimulator | None = None) -> None:
        self.simulator = simulator or StrategySimulator()
        self.owns_simulator = simulator is None

    def close(self) -> None:
        if self.owns_simulator:
            self.simulator.close()

    def predict(self, meeting_key: int | None = None) -> ClassificationResponse:
        strategy: StrategyResponse = self.simulator.simulate_grid(meeting_key)
        return self.from_strategy(strategy)

    @staticmethod
    def from_strategy(strategy: StrategyResponse) -> ClassificationResponse:
        ordered = sorted(strategy.drivers, key=lambda d: d.predicted_race_time_s)
        leader_time = ordered[0].predicted_race_time_s if ordered else 0.0
        n = max(len(ordered), 1)
        standings: list[PredictedFinish] = []
        for idx, driver in enumerate(ordered, start=1):
            # Confidence decays gently with predicted position (heuristic, not calibrated probs)
            confidence = round(max(0.35, 1.0 - (idx - 1) / (n * 1.35)), 3)
            standings.append(
                PredictedFinish(
                    position=idx,
                    driver_number=driver.driver_number,
                    name_acronym=driver.name_acronym,
                    full_name=driver.full_name,
                    team_name=driver.team_name,
                    team_colour=driver.team_colour,
                    estimated_race_time_s=round(driver.predicted_race_time_s, 3),
                    gap_to_leader_s=round(driver.predicted_race_time_s - leader_time, 3),
                    strategy_label=driver.strategy_label,
                    confidence=confidence,
                )
            )
        return ClassificationResponse(
            meeting=strategy.meeting,
            standings=standings,
            model_version="ranking-strategy-v1",
            generated_at=datetime.now(timezone.utc).isoformat(),
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
        """Fast ranking for historical backtests (no full strategy search)."""
        rows: list[tuple[float, dict]] = []
        for _, row in drivers_df.iterrows():
            driver = row.to_dict()
            dnum = int(driver["driver_number"])
            # Assume typical 1-stop dry race: baseline pace + driver offset + one pit
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
                    strategy_label="pace-baseline 1-stop",
                    confidence=round(max(0.35, 1.0 - (idx - 1) / (n * 1.35)), 3),
                )
            )
        return out
