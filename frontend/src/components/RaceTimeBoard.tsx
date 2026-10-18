"use client";

import { useCallback, useEffect, useState } from "react";
import {
  fetchPrediction,
  formatRaceTime,
  type ClassificationResponse,
  type PredictedFinish,
} from "@/lib/api";
import { ClassificationDetail } from "./ClassificationDetail";

type Props = {
  meetingKey: number | null;
  active: boolean;
};

function formatGap(seconds: number): string {
  if (seconds <= 0) return "—";
  return `+${seconds.toFixed(3)}`;
}

export function RaceTimeBoard({ meetingKey, active }: Props) {
  const [prediction, setPrediction] = useState<ClassificationResponse | null>(null);
  const [loadedKey, setLoadedKey] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<PredictedFinish | null>(null);

  const load = useCallback(async (key: number) => {
    setLoading(true);
    setError(null);
    setSelected(null);
    try {
      setPrediction(await fetchPrediction(key));
      setLoadedKey(key);
    } catch (err) {
      setPrediction(null);
      setLoadedKey(null);
      setError(err instanceof Error ? err.message : "Prediction failed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!active || meetingKey == null || loadedKey === meetingKey) return;
    void load(meetingKey);
  }, [active, meetingKey, loadedKey, load]);

  useEffect(() => {
    if (meetingKey == null) return;
    if (loadedKey != null && loadedKey !== meetingKey) {
      setPrediction(null);
      setLoadedKey(null);
      setSelected(null);
    }
  }, [meetingKey, loadedKey]);

  if (!active) return null;

  const ordered = prediction
    ? [...prediction.standings]
        .filter((r) => r.estimated_race_time_s != null)
        .sort((a, b) => (a.estimated_race_time_s ?? 0) - (b.estimated_race_time_s ?? 0))
    : [];
  const leader = ordered[0]?.estimated_race_time_s ?? 0;

  return (
    <>
      {error && (
        <div className="border border-accent/40 bg-accent/10 px-4 py-3 text-sm text-white">{error}</div>
      )}
      {loading && (
        <div className="animate-pulse border border-white/10 bg-panel/60 px-4 py-8 text-center text-sm text-muted">
          Predicting race times…
        </div>
      )}

      {!loading && prediction && (
        <section className="space-y-3">
          <div className="flex flex-wrap items-baseline justify-between gap-3">
            <h2 className="font-display text-2xl tracking-wide text-white">Predicted race times</h2>
            <p className="text-xs text-muted">{prediction.model_version}</p>
          </div>
          <p className="text-xs text-fog">
            Pace-estimated race times from Classification for now — green-flag pace × race distance, not
            Strategy wall-clock. A dedicated race-time model can replace this later.
          </p>
          <div className="overflow-x-auto rounded-sm border border-white/10 bg-panel/80 backdrop-blur">
            <table className="w-full min-w-[640px] border-collapse text-left text-sm">
              <thead>
                <tr className="border-b border-white/10 text-[11px] uppercase tracking-[0.14em] text-muted">
                  <th className="px-4 py-3 font-medium">Pos</th>
                  <th className="px-4 py-3 font-medium">Driver</th>
                  <th className="px-4 py-3 font-medium">Team</th>
                  <th className="px-4 py-3 font-medium">Pace est. time</th>
                  <th className="px-4 py-3 font-medium">Gap</th>
                  <th className="px-4 py-3 font-medium">Source</th>
                </tr>
              </thead>
              <tbody>
                {ordered.map((row, idx) => {
                  const activeRow = selected?.driver_number === row.driver_number;
                  const time = row.estimated_race_time_s ?? 0;
                  return (
                    <tr
                      key={row.driver_number}
                      onClick={() => setSelected(row)}
                      className={`cursor-pointer border-b border-white/5 transition-colors ${
                        activeRow ? "bg-accent/15" : "hover:bg-white/5"
                      }`}
                    >
                      <td className="px-4 py-3 font-display text-xl text-accent">{idx + 1}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          <span
                            className="h-8 w-1 rounded-full"
                            style={{
                              backgroundColor: row.team_colour ? `#${row.team_colour}` : "#e10600",
                            }}
                          />
                          <div>
                            <div className="font-display text-lg leading-none tracking-wide">
                              {row.name_acronym}
                            </div>
                            <div className="text-xs text-muted">{row.full_name}</div>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-muted">{row.team_name}</td>
                      <td className="px-4 py-3 font-mono text-accent">{formatRaceTime(time)}</td>
                      <td className="px-4 py-3 font-mono text-fog">{formatGap(time - leader)}</td>
                      <td className="px-4 py-3 text-xs text-muted">{row.strategy_label ?? "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {selected && <ClassificationDetail row={selected} />}
        </section>
      )}
    </>
  );
}
