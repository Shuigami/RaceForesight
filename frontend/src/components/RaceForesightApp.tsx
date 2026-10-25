"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  fetchRaces,
  fetchStrategy,
  savePredictions,
  type MeetingSummary,
  type StrategyResponse,
} from "@/lib/api";
import { ClassificationBoard } from "./ClassificationBoard";
import { ExplainPanel } from "./ExplainPanel";
import { RaceTimeBoard } from "./RaceTimeBoard";
import { StrategyGrid } from "./StrategyGrid";

type RaceView = "classification" | "race-time" | "strategy";

function parseView(raw: string | null): RaceView {
  if (raw === "strategy") return "strategy";
  if (raw === "race-time") return "race-time";
  return "classification";
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
  const [loadingRaces, setLoadingRaces] = useState(true);
  const [loadingStrategy, setLoadingStrategy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
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
    if (view !== "strategy" || meetingKey == null || strategyKey === meetingKey) return;
    void loadStrategy(meetingKey);
  }, [view, meetingKey, strategyKey, loadStrategy]);

  useEffect(() => {
    if (meetingKey == null) return;
    if (strategyKey != null && strategyKey !== meetingKey) {
      setStrategy(null);
      setStrategyKey(null);
    }
  }, [meetingKey, strategyKey]);

  const onSaveResults = async () => {
    if (meetingKey == null) return;
    setSaving(true);
    setSaveMsg(null);
    setError(null);
    try {
      const data = await savePredictions(meetingKey);
      const snap = data.snapshot;
      const overwritten = snap.first_saved_at !== snap.saved_at;
      const when = new Date(snap.saved_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      setSaveMsg(overwritten ? `Overwritten · ${when}` : `Saved · ${when}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
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
            race pace with a shared race shape. Its finishing order will not match a pure pace-time sort.
          </p>
          <p>
            <strong className="text-white">Race time</strong> predicts total race duration per driver
            with a dedicated regressor (grid + form + pace + distance). Not finishing order and not
            Strategy tyre wall-clock.
          </p>
          <p>
            <strong className="text-white">Strategy</strong> ranks the fastest dry tyre / pit plans for
            the race (top 4), with predicted gaps between them — not per-driver optimisation.
          </p>
        </ExplainPanel>

        <div className="flex flex-wrap items-end gap-4 pt-2">
          <label className="flex min-w-[240px] flex-col gap-2">
            <span className="text-[11px] uppercase tracking-[0.16em] text-muted">Grand Prix</span>
            <select
              className="border border-white/15 bg-ink-850 px-3 py-2.5 text-sm text-white outline-none focus:border-accent"
              disabled={loadingRaces || races.length === 0}
              value={meetingKey ?? ""}
              onChange={(e) => {
                setMeetingKey(Number(e.target.value));
                setSaveMsg(null);
              }}
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
          <button
            type="button"
            disabled={meetingKey == null || saving}
            onClick={() => void onSaveResults()}
            className="border border-accent bg-accent/20 px-4 py-2.5 text-[11px] uppercase tracking-[0.16em] text-white transition-colors hover:bg-accent/30 disabled:opacity-40"
          >
            {saving ? "Saving…" : "Save results"}
          </button>
          {saveMsg && <p className="pb-1 text-sm text-fog">{saveMsg}</p>}
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

      {error && (
        <div className="border border-accent/40 bg-accent/10 px-4 py-3 text-sm text-white">{error}</div>
      )}

      <RaceTimeBoard meetingKey={meetingKey} active={view === "race-time"} />

      {view === "strategy" && (
        <>
          {loadingStrategy && (
            <div className="animate-pulse border border-white/10 bg-panel/60 px-4 py-8 text-center text-sm text-muted">
              Ranking dry tyre strategies…
            </div>
          )}

          {!loadingStrategy && strategy && (
            <section className="space-y-3">
              <div className="flex items-baseline justify-between gap-3">
                <h2 className="font-display text-2xl tracking-wide text-white">
                  Top tyre strategies
                </h2>
                <p className="text-xs text-muted">{strategy.model_version}</p>
              </div>
              <StrategyGrid strategies={strategy.strategies} actual={strategy.actual} />
            </section>
          )}
        </>
      )}

      <ClassificationBoard meetingKey={meetingKey} active={view === "classification"} />
    </main>
  );
}
