"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  fetchDriverStrategy,
  fetchRaces,
  fetchStrategy,
  type MeetingSummary,
  type StrategyDetail,
  type StrategyResponse,
} from "@/lib/api";
import { ClassificationBoard } from "./ClassificationBoard";
import { DriverDetail } from "./DriverDetail";
import { ExplainPanel } from "./ExplainPanel";
import { RaceTimeBoard } from "./RaceTimeBoard";
import { StrategyGrid } from "./StrategyGrid";

type RaceView = "classification" | "race-time" | "strategy";

function parseView(raw: string | null): RaceView {
  if (raw === "strategy") return "strategy";
  if (raw === "race-time") return "race-time";
  return "classification";
}

function usesStrategyData(view: RaceView): boolean {
  return view === "strategy" || view === "race-time";
}

export function RaceForesightApp() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const view = parseView(searchParams.get("view"));

  const [races, setRaces] = useState<MeetingSummary[]>([]);
  const [meetingKey, setMeetingKey] = useState<number | null>(null);
  const [strategy, setStrategy] = useState<StrategyResponse | null>(null);
  const [strategyKey, setStrategyKey] = useState<number | null>(null);
  const [detail, setDetail] = useState<StrategyDetail | null>(null);
  const [selectedDriver, setSelectedDriver] = useState<number | null>(null);
  const [loadingRaces, setLoadingRaces] = useState(true);
  const [loadingStrategy, setLoadingStrategy] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const setView = (next: RaceView) => {
    const params = new URLSearchParams(searchParams.toString());
    if (next === "classification") params.delete("view");
    else params.set("view", next);
    const qs = params.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  };

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
      setStrategyKey(key);
    } catch (err) {
      setStrategy(null);
      setStrategyKey(null);
      setError(err instanceof Error ? err.message : "Strategy request failed");
    } finally {
      setLoadingStrategy(false);
    }
  }, []);

  useEffect(() => {
    if (!usesStrategyData(view) || meetingKey == null || strategyKey === meetingKey) return;
    void loadStrategy(meetingKey);
  }, [view, meetingKey, strategyKey, loadStrategy]);

  useEffect(() => {
    if (meetingKey == null) return;
    if (strategyKey != null && strategyKey !== meetingKey) {
      setStrategy(null);
      setStrategyKey(null);
      setDetail(null);
      setSelectedDriver(null);
    }
  }, [meetingKey, strategyKey]);

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

  const tabClass = (active: boolean) =>
    `px-4 py-2 text-[11px] uppercase tracking-[0.16em] transition-colors border-b-2 ${
      active
        ? "border-accent text-accent"
        : "border-transparent text-muted hover:text-white"
    }`;

  return (
    <main className="relative mx-auto flex w-full max-w-6xl flex-col gap-10 px-5 pb-16 pt-10 md:px-8">
      <header className="space-y-5">
        <p className="text-[11px] uppercase tracking-[0.28em] text-accent">Predictive race foresight</p>
        <h1 className="font-display text-5xl leading-none tracking-[0.04em] text-white md:text-7xl">
          Race
        </h1>
        <p className="max-w-xl text-base text-fog md:text-lg">
          Three views for the same Grand Prix — finishing order, race times, then tyre plans.
        </p>

        <ExplainPanel title="Three views, one race">
          <p>
            <strong className="text-white">Classification</strong> ranks who finishes where from relative
            race pace with a shared race shape. Its order and times will not match Race time or Strategy.
          </p>
          <p>
            <strong className="text-white">Race time</strong> compares predicted race duration under each
            driver’s own optimal dry plan. For now it reuses the strategy lap model; a dedicated race-time
            model can replace that later.
          </p>
          <p>
            <strong className="text-white">Strategy</strong> finds the fastest dry tyre / pit plan for
            each driver. Useful to compare plans, not to call the result.
          </p>
        </ExplainPanel>

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
              {selectedMeeting.circuit_short_name || selectedMeeting.country_name} ·{" "}
              {selectedMeeting.race_laps} laps
            </div>
          )}
        </div>

        <div className="flex gap-1 border-b border-white/10" role="tablist" aria-label="Race views">
          <button
            type="button"
            role="tab"
            aria-selected={view === "classification"}
            className={tabClass(view === "classification")}
            onClick={() => setView("classification")}
          >
            Classification
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={view === "race-time"}
            className={tabClass(view === "race-time")}
            onClick={() => setView("race-time")}
          >
            Race time
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={view === "strategy"}
            className={tabClass(view === "strategy")}
            onClick={() => setView("strategy")}
          >
            Strategy
          </button>
        </div>
      </header>

      {error && usesStrategyData(view) && (
        <div className="border border-accent/40 bg-accent/10 px-4 py-3 text-sm text-white">{error}</div>
      )}

      {view === "race-time" && (
        <>
          {loadingStrategy && (
            <div className="animate-pulse border border-white/10 bg-panel/60 px-4 py-8 text-center text-sm text-muted">
              Predicting race times…
            </div>
          )}

          {!loadingStrategy && strategy && (
            <>
              <section className="space-y-3">
                <div className="flex flex-wrap items-baseline justify-between gap-3">
                  <h2 className="font-display text-2xl tracking-wide text-white">Predicted race times</h2>
                  <p className="text-xs text-muted">{strategy.model_version}</p>
                </div>
                <p className="text-xs text-fog">
                  Based on the strategy lap model for now — a dedicated race-time model can replace this
                  later. Times assume each driver runs their own optimal dry plan.
                </p>
                <RaceTimeBoard
                  drivers={strategy.drivers}
                  selected={selectedDriver}
                  onSelect={onSelectDriver}
                />
              </section>

              {loadingDetail && <div className="text-sm text-muted">Loading driver detail…</div>}
              {detail && !loadingDetail && <DriverDetail detail={detail} />}
            </>
          )}
        </>
      )}

      {view === "strategy" && (
        <>
          {loadingStrategy && (
            <div className="animate-pulse border border-white/10 bg-panel/60 px-4 py-8 text-center text-sm text-muted">
              Simulating pit windows for the grid…
            </div>
          )}

          {!loadingStrategy && strategy && (
            <>
              <section className="space-y-3">
                <div className="flex items-baseline justify-between gap-3">
                  <h2 className="font-display text-2xl tracking-wide text-white">
                    Optimal tyre strategies
                  </h2>
                  <p className="text-xs text-muted">{strategy.model_version}</p>
                </div>
                <StrategyGrid
                  drivers={strategy.drivers}
                  actual={strategy.actual}
                  selected={selectedDriver}
                  onSelect={onSelectDriver}
                />
              </section>

              {loadingDetail && <div className="text-sm text-muted">Loading driver detail…</div>}
              {detail && !loadingDetail && <DriverDetail detail={detail} />}
            </>
          )}
        </>
      )}

      <ClassificationBoard meetingKey={meetingKey} active={view === "classification"} />
    </main>
  );
}
