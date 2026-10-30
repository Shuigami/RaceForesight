"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  fetchRaces,
  fetchSavedPredictions,
  mediaUrl,
  withMeetingArt,
  type MeetingSummary,
  type PredictionMeetingListItem,
} from "@/lib/api";
import { CircuitThumb } from "./CircuitThumb";
import { ExplainPanel } from "./ExplainPanel";

function fmtWhen(iso: string | null | undefined) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString([], {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

export function ResultsDashboard() {
  const [list, setList] = useState<PredictionMeetingListItem[]>([]);
  const [races, setRaces] = useState<MeetingSummary[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadList = useCallback(async () => {
    setLoadingList(true);
    setError(null);
    try {
      const [preds, raceList] = await Promise.all([
        fetchSavedPredictions(),
        fetchRaces().catch(() => [] as MeetingSummary[]),
      ]);
      setRaces(raceList);
      setList(preds);
    } catch (err) {
      setList([]);
      setError(err instanceof Error ? err.message : "Failed to load saved predictions");
    } finally {
      setLoadingList(false);
    }
  }, []);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  const displayList = useMemo(
    () => list.map((item) => withMeetingArt(item, races)),
    [list, races],
  );

  const stats = useMemo(() => {
    const scored = displayList.filter((i) => i.status === "scored").length;
    const saves = displayList.reduce((n, i) => n + i.save_count, 0);
    return { gps: displayList.length, scored, pending: displayList.length - scored, saves };
  }, [displayList]);

  return (
    <main className="relative mx-auto flex w-full max-w-6xl flex-col gap-10 px-5 pb-16 pt-10 md:px-8">
      <header className="space-y-6">
        <div className="space-y-3">
          <p className="text-[11px] uppercase tracking-[0.28em] text-accent">Locked predictions</p>
          <h1 className="font-display text-5xl leading-none tracking-[0.04em] text-white md:text-7xl">
            Results
          </h1>
          <p className="max-w-xl text-base text-fog md:text-lg">
            Saved forecasts scored against the real race — pick a GP, open a snapshot.
          </p>
        </div>

        {!loadingList && displayList.length > 0 && (
          <div className="grid grid-cols-2 gap-px overflow-hidden border border-white/10 bg-white/10 sm:grid-cols-4">
            {[
              { label: "GPs", value: String(stats.gps).padStart(2, "0") },
              { label: "Scored", value: String(stats.scored).padStart(2, "0") },
              { label: "Pending", value: String(stats.pending).padStart(2, "0") },
              { label: "Saves", value: String(stats.saves).padStart(2, "0") },
            ].map((s) => (
              <div key={s.label} className="bg-ink-850 px-4 py-4">
                <p className="text-[10px] uppercase tracking-[0.22em] text-muted">{s.label}</p>
                <p className="mt-1 font-display text-3xl tracking-wide text-white md:text-4xl">
                  {s.value}
                </p>
              </div>
            ))}
          </div>
        )}

        <ExplainPanel title="How to read this">
          <p>
            Save from Race as many times as you want. Each GP lists its saves; rename or delete
            there, then open a save to score against the real race.
          </p>
          <p>
            <strong className="text-white">Scored</strong> means OpenF1 has finishing results —
            it does not retrain the models. Integrity badges flag pre-race saves, post-race
            saves, and train overlap (model trained after lights out).
          </p>
        </ExplainPanel>
      </header>

      {loadingList && (
        <div className="animate-pulse border border-white/10 bg-panel/60 px-4 py-8 text-center text-sm text-muted">
          Loading saved GPs…
        </div>
      )}

      {error && (
        <div className="border border-accent/40 bg-accent/10 px-4 py-3 text-sm text-white">{error}</div>
      )}

      {!loadingList && displayList.length === 0 && (
        <div className="relative overflow-hidden border border-dashed border-white/20 bg-ink-850 px-6 py-14 text-center">
          <p className="font-display text-2xl tracking-wide text-white">No snapshots yet</p>
          <p className="mt-2 text-sm text-fog">Open Race, pick a GP, hit Save results.</p>
          <Link
            href="/"
            className="mt-6 inline-block border border-accent bg-accent/20 px-4 py-2.5 text-[11px] uppercase tracking-[0.16em] text-white hover:bg-accent/30"
          >
            Go to Race
          </Link>
        </div>
      )}

      {displayList.length > 0 && (
        <ul className="flex flex-col gap-3">
          {displayList.map((item, idx) => (
            <li key={item.meeting_key} className="rf-fade-in" style={{ animationDelay: `${idx * 40}ms` }}>
              <Link
                href={`/results/${item.meeting_key}`}
                className="group relative block overflow-hidden border border-white/10 bg-panel/90 transition-colors hover:border-accent/50"
                style={{ clipPath: "polygon(0 0, 100% 0, 100% 92%, 98.5% 100%, 0 100%)" }}
              >
                {mediaUrl(item.circuit_image) && (
                  <div className="pointer-events-none absolute inset-y-0 right-0 w-2/5 opacity-25 transition-opacity group-hover:opacity-40">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={mediaUrl(item.circuit_image)!}
                      alt=""
                      className="absolute inset-0 h-full w-full object-contain object-right pr-3 brightness-0 invert"
                    />
                    <div className="absolute inset-0 bg-gradient-to-r from-panel via-panel/80 to-transparent" />
                  </div>
                )}
                <div className="pointer-events-none absolute left-0 top-0 h-full w-1 bg-accent/0 transition-colors group-hover:bg-accent" />
                <div className="relative flex flex-wrap items-center justify-between gap-4 px-4 py-5 md:px-5">
                  <div className="flex min-w-0 items-center gap-4">
                    <CircuitThumb
                      label={item.circuit_short_name || item.meeting_name}
                      circuitImage={item.circuit_image}
                      countryFlag={item.country_flag}
                      size={64}
                    />
                    <div className="min-w-0 space-y-1">
                      <p className="text-[10px] uppercase tracking-[0.22em] text-muted">
                        {item.year ?? "—"}
                        {item.circuit_short_name ? ` · ${item.circuit_short_name}` : ""}
                      </p>
                      <p className="truncate font-display text-2xl tracking-wide text-white md:text-3xl">
                        {item.meeting_name}
                      </p>
                      <p className="font-mono text-xs text-fog">
                        Race {fmtWhen(item.race_start_at)}
                        {"  ·  "}
                        {item.save_count} save{item.save_count === 1 ? "" : "s"}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span
                      className={`border px-3 py-1.5 text-[11px] uppercase tracking-[0.14em] ${
                        item.status === "scored"
                          ? "border-accent/50 bg-accent/15 text-white"
                          : "border-white/15 text-muted"
                      }`}
                    >
                      {item.status === "scored" ? "Scored" : "Pending"}
                    </span>
                    <span className="hidden text-[11px] uppercase tracking-[0.16em] text-muted transition-colors group-hover:text-accent sm:inline">
                      Open →
                    </span>
                  </div>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
