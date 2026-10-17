"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchDriverStrategy,
  fetchRaces,
  fetchStrategy,
  type MeetingSummary,
  type StrategyDetail,
  type StrategyResponse,
} from "@/lib/api";
import { DriverDetail } from "./DriverDetail";
import { StrategyGrid } from "./StrategyGrid";

export function RaceForesightApp() {
  const [races, setRaces] = useState<MeetingSummary[]>([]);
  const [meetingKey, setMeetingKey] = useState<number | null>(null);
  const [strategy, setStrategy] = useState<StrategyResponse | null>(null);
  const [detail, setDetail] = useState<StrategyDetail | null>(null);
  const [selectedDriver, setSelectedDriver] = useState<number | null>(null);
  const [loadingRaces, setLoadingRaces] = useState(true);
  const [loadingStrategy, setLoadingStrategy] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setLoadingRaces(true);
        const data = await fetchRaces();
        if (cancelled) return;
        setRaces(data);
        const def = data.find((r) => r.is_default) ?? data[data.length - 1];
        if (def) setMeetingKey(def.meeting_key);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load races");
      } finally {
        if (!cancelled) setLoadingRaces(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const loadStrategy = useCallback(async (key: number) => {
    setLoadingStrategy(true);
    setError(null);
    setDetail(null);
    setSelectedDriver(null);
    try {
      const data = await fetchStrategy(key);
      setStrategy(data);
    } catch (err) {
      setStrategy(null);
      setError(err instanceof Error ? err.message : "Strategy request failed");
    } finally {
      setLoadingStrategy(false);
    }
  }, []);

  useEffect(() => {
    if (meetingKey != null) {
      void loadStrategy(meetingKey);
    }
  }, [meetingKey, loadStrategy]);

  const onSelectDriver = async (driverNumber: number) => {
    if (meetingKey == null) return;
    setSelectedDriver(driverNumber);
    setLoadingDetail(true);
    try {
      const data = await fetchDriverStrategy(meetingKey, driverNumber);
      setDetail(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Driver detail failed");
    } finally {
      setLoadingDetail(false);
    }
  };

  const selectedMeeting = useMemo(
    () => races.find((r) => r.meeting_key === meetingKey) ?? strategy?.meeting ?? null,
    [races, meetingKey, strategy],
  );

  return (
      <main className="relative mx-auto flex w-full max-w-6xl flex-col gap-10 px-5 pb-16 pt-10 md:px-8">
        <header className="space-y-5">
          <p className="text-[11px] uppercase tracking-[0.28em] text-accent">Predictive race strategy</p>
          <h1 className="font-display text-5xl leading-none tracking-[0.04em] text-white md:text-7xl">
            Tyre strategy
          </h1>
          <p className="max-w-xl text-base text-fog md:text-lg">
            XGBoost lap-time estimates and pit-window simulation for the full F1 grid — defaulting to the next Grand Prix.
          </p>

          <div className="flex flex-wrap items-end gap-4 pt-2">
            <label className="flex min-w-[240px] flex-col gap-2">
              <span className="text-[11px] uppercase tracking-[0.16em] text-muted">Grand Prix</span>
              <select
                className="border border-white/15 bg-ink-850 px-3 py-2.5 text-sm text-white outline-none focus:border-accent"
                disabled={loadingRaces || races.length === 0}
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
            {selectedMeeting && (
              <div className="pb-1 text-sm text-muted">
                {selectedMeeting.circuit_short_name || selectedMeeting.country_name} · {selectedMeeting.race_laps} laps
              </div>
            )}
          </div>
        </header>

        {error && (
          <div className="border border-accent/40 bg-accent/10 px-4 py-3 text-sm text-white">
            {error}
          </div>
        )}

        {loadingStrategy && (
          <div className="animate-pulse border border-white/10 bg-panel/60 px-4 py-8 text-center text-sm text-muted">
            Simulating pit windows for the grid…
          </div>
        )}

        {!loadingStrategy && strategy && (
          <>
            <section className="space-y-3">
              <div className="flex items-baseline justify-between gap-3">
                <h2 className="font-display text-2xl tracking-wide text-white">Optimal tyre strategies</h2>
                <p className="text-xs text-muted">{strategy.model_version}</p>
              </div>
              <StrategyGrid
                drivers={strategy.drivers}
                selected={selectedDriver}
                onSelect={onSelectDriver}
              />
            </section>

            {loadingDetail && (
              <div className="text-sm text-muted">Loading driver detail…</div>
            )}
            {detail && !loadingDetail && <DriverDetail detail={detail} />}
          </>
        )}
      </main>
  );
}
