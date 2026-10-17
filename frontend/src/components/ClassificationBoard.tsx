"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchPrediction,
  fetchRaces,
  formatRaceTime,
  type ClassificationResponse,
  type MeetingSummary,
} from "@/lib/api";
import { ExplainPanel } from "./ExplainPanel";

export function ClassificationBoard() {
  const [races, setRaces] = useState<MeetingSummary[]>([]);
  const [meetingKey, setMeetingKey] = useState<number | null>(null);
  const [prediction, setPrediction] = useState<ClassificationResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await fetchRaces();
        if (cancelled) return;
        setRaces(data);
        const def = data.find((r) => r.is_default) ?? data[data.length - 1];
        if (def) setMeetingKey(def.meeting_key);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load races");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const load = useCallback(async (key: number) => {
    setLoading(true);
    setError(null);
    try {
      setPrediction(await fetchPrediction(key));
    } catch (err) {
      setPrediction(null);
      setError(err instanceof Error ? err.message : "Prediction failed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (meetingKey != null) void load(meetingKey);
  }, [meetingKey, load]);

  const selected = useMemo(
    () => races.find((r) => r.meeting_key === meetingKey) ?? prediction?.meeting ?? null,
    [races, meetingKey, prediction],
  );

  return (
    <main className="relative mx-auto flex w-full max-w-6xl flex-col gap-8 px-5 pb-16 pt-10 md:px-8">
      <header className="space-y-4">
        <p className="text-[11px] uppercase tracking-[0.28em] text-accent">Phase 2</p>
        <h1 className="font-display text-5xl tracking-[0.04em] text-white md:text-6xl">
          Predicted classification
        </h1>
        <p className="max-w-2xl text-fog">
          Who finishes where, from relative race pace — a different question than Strategy&apos;s
          per-driver tyre optimisation.
        </p>

        <ExplainPanel title="Strategy vs Classification">
          <p>
            <strong className="text-white">Strategy</strong> searches tyre compounds and pit windows so
            each driver gets their own optimal plan (and a strategy race time under that plan).
          </p>
          <p>
            <strong className="text-white">Classification</strong> ranks the grid with a shared dry-race
            shape: circuit baseline lap + each driver&apos;s recent pace offset + one typical pit stop.
            No per-driver tyre-window search — so <em>est. times here will not match Strategy</em>.
          </p>
          <p>
            <strong className="text-white">Pos</strong> is the main output. Est. time / gap are secondary
            pace estimates. Confidence is a simple heuristic, not a win probability — see{" "}
            <strong className="text-white">Models</strong> for backtest scores.
          </p>
        </ExplainPanel>

        <label className="flex min-w-[240px] max-w-md flex-col gap-2">
          <span className="text-[11px] uppercase tracking-[0.16em] text-muted">Grand Prix</span>
          <select
            className="border border-white/15 bg-ink-850 px-3 py-2.5 text-sm text-white outline-none focus:border-accent"
            value={meetingKey ?? ""}
            onChange={(e) => setMeetingKey(Number(e.target.value))}
          >
            {races.map((race) => (
              <option key={race.meeting_key} value={race.meeting_key}>
                {race.year} · {race.meeting_name}
                {race.is_default ? " (next)" : ""}
              </option>
            ))}
          </select>
        </label>
        {selected && (
          <p className="text-sm text-muted">
            {selected.circuit_short_name || selected.country_name} · {selected.race_laps} laps
          </p>
        )}
      </header>

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
    </main>
  );
}
