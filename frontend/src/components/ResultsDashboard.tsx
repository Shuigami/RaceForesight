"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  fetchSavedPredictions,
  type PredictionMeetingListItem,
} from "@/lib/api";
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
  const [loadingList, setLoadingList] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadList = useCallback(async () => {
    setLoadingList(true);
    setError(null);
    try {
      setList(await fetchSavedPredictions());
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

  return (
    <main className="relative mx-auto flex w-full max-w-6xl flex-col gap-8 px-5 pb-16 pt-10 md:px-8">
      <header className="space-y-5">
        <p className="text-[11px] uppercase tracking-[0.28em] text-accent">Locked predictions</p>
        <h1 className="font-display text-5xl leading-none tracking-[0.04em] text-white md:text-7xl">
          Results
        </h1>
        <p className="max-w-xl text-base text-fog md:text-lg">
          GPs with at least one saved forecast — open a race to manage saves and compare.
        </p>
        <ExplainPanel title="How to read this">
          <p>
            Save from Race as many times as you want. Each GP lists its saves; rename or delete
            there, then open a save to score against the real race.
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

      {!loadingList && list.length === 0 && (
        <div className="border border-white/10 bg-panel/60 px-4 py-8 text-center text-sm text-fog">
          No snapshots yet. Open Race, pick a GP, hit Save results.
        </div>
      )}

      {list.length > 0 && (
        <ul className="divide-y divide-white/10 border border-white/10 bg-panel/80">
          {list.map((item) => (
            <li key={item.meeting_key}>
              <Link
                href={`/results/${item.meeting_key}`}
                className="flex flex-wrap items-baseline justify-between gap-3 px-4 py-4 transition hover:bg-white/5"
              >
                <div className="space-y-1">
                  <p className="text-base text-white">
                    {item.year ? `${item.year} · ` : ""}
                    {item.meeting_name}
                  </p>
                  <p className="text-xs text-muted">
                    Race {fmtWhen(item.race_start_at)}
                    {" · "}
                    {item.save_count} save{item.save_count === 1 ? "" : "s"}
                  </p>
                </div>
                <span
                  className={`text-[11px] uppercase tracking-[0.14em] ${
                    item.status === "scored" ? "text-accent" : "text-muted"
                  }`}
                >
                  {item.status === "scored" ? "Scored" : "Pending"}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
