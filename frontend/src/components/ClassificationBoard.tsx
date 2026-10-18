"use client";

import { useCallback, useEffect, useState } from "react";
import {
  fetchPrediction,
  formatRaceTime,
  type ClassificationResponse,
} from "@/lib/api";

type Props = {
  meetingKey: number | null;
  active: boolean;
};

export function ClassificationBoard({ meetingKey, active }: Props) {
  const [prediction, setPrediction] = useState<ClassificationResponse | null>(null);
  const [loadedKey, setLoadedKey] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (key: number) => {
    setLoading(true);
    setError(null);
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
    }
  }, [meetingKey, loadedKey]);

  if (!active) return null;

  return (
    <>
      {error && (
        <div className="border border-accent/40 bg-accent/10 px-4 py-3 text-sm text-white">{error}</div>
      )}
      {loading && (
        <div className="animate-pulse border border-white/10 bg-panel/60 px-4 py-8 text-center text-sm text-muted">
          Ranking the grid…
        </div>
      )}

      {!loading && prediction && (
        <section className="space-y-3">
          <div className="flex flex-wrap items-baseline justify-between gap-3">
            <h2 className="font-display text-2xl tracking-wide text-white">Standings</h2>
            <p className="text-xs text-muted">{prediction.model_version}</p>
          </div>
          <p className="text-xs text-fog">{prediction.note}</p>
          <p className="text-xs text-muted">
            Pos is the main output. Pace est. time / gap are green-flag estimates (not wall-clock race
            times) and will not match Strategy race times.
          </p>
          <div className="overflow-x-auto rounded-sm border border-white/10 bg-panel/80 backdrop-blur">
            <table className="w-full min-w-[640px] border-collapse text-left text-sm">
              <thead>
                <tr className="border-b border-white/10 text-[11px] uppercase tracking-[0.14em] text-muted">
                  <th className="px-4 py-3 font-medium">Pos</th>
                  <th className="px-4 py-3 font-medium">Driver</th>
                  <th className="px-4 py-3 font-medium">Team</th>
                  <th className="px-4 py-3 font-medium">Confidence</th>
                  <th className="px-4 py-3 font-medium text-right">Pace est. time</th>
                  <th className="px-4 py-3 font-medium text-right">Gap</th>
                </tr>
              </thead>
              <tbody>
                {prediction.standings.map((row) => (
                  <tr key={row.driver_number} className="border-b border-white/5">
                    <td className="px-4 py-3 font-display text-xl text-accent">{row.position}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        <span
                          className="h-8 w-1 rounded-full"
                          style={{ backgroundColor: row.team_colour ? `#${row.team_colour}` : "#e10600" }}
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
                    <td className="px-4 py-3">
                      <div className="h-1.5 w-24 overflow-hidden bg-white/10">
                        <div
                          className="h-full bg-accent"
                          style={{ width: `${Math.round((row.confidence ?? 0) * 100)}%` }}
                        />
                      </div>
                      <span className="mt-1 inline-block font-mono text-[11px] text-fog">
                        {row.confidence != null ? `${Math.round(row.confidence * 100)}%` : "—"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-fog">
                      {row.estimated_race_time_s != null ? formatRaceTime(row.estimated_race_time_s) : "—"}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-muted">
                      {row.gap_to_leader_s != null && row.gap_to_leader_s > 0
                        ? `+${row.gap_to_leader_s.toFixed(1)}s`
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  );
}
