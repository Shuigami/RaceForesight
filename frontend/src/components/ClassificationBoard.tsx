"use client";

import { useCallback, useEffect, useState } from "react";
import {
  fetchPrediction,
  type ClassificationResponse,
  type PredictedFinish,
} from "@/lib/api";
import { ClassificationDetail } from "./ClassificationDetail";
import { DriverAvatar } from "./DriverAvatar";

type Props = {
  meetingKey: number | null;
  active: boolean;
};

export function ClassificationBoard({ meetingKey, active }: Props) {
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
          <div className="rf-table-wrap border border-white/10 bg-panel/90">
            <table className="min-w-[520px] text-left text-sm">
              <thead>
                <tr className="border-b border-white/10 bg-ink-850/80 text-[11px] uppercase tracking-[0.14em] text-muted">
                  <th className="px-4 py-3 font-medium">Pos</th>
                  <th className="px-4 py-3 font-medium">Driver</th>
                  <th className="px-4 py-3 font-medium">Team</th>
                  <th className="px-4 py-3 font-medium">Confidence</th>
                </tr>
              </thead>
              <tbody>
                {prediction.standings.map((row) => {
                  const activeRow = selected?.driver_number === row.driver_number;
                  return (
                    <tr
                      key={row.driver_number}
                      onClick={() => setSelected(row)}
                      className={`rf-row-hover cursor-pointer border-b border-white/5 ${
                        activeRow ? "bg-accent/15" : "hover:bg-white/[0.04]"
                      }`}
                    >
                      <td className="rf-pos px-4 py-3 font-display text-xl text-accent">
                        {String(row.position).padStart(2, "0")}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          <DriverAvatar
                            name={row.full_name}
                            acronym={row.name_acronym}
                            headshotUrl={row.headshot_url}
                            teamColour={row.team_colour}
                          />
                          <div className="text-sm text-white">{row.full_name}</div>
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
